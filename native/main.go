package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"time"

	"cuelang.org/go/internal/mod/modrequirements"
	"cuelang.org/go/mod/modconfig"
	"cuelang.org/go/mod/modfile"
	"cuelang.org/go/mod/modregistry"
	"cuelang.org/go/mod/module"
	"cuelang.org/go/mod/modzip"
)

func must[T any](value T, err error) T {
	if err != nil {
		panic(err)
	}
	return value
}
func check(err error) {
	if err != nil {
		panic(err)
	}
}
func digest(data []byte) string {
	v := sha256.Sum256(data)
	return "sha256:" + hex.EncodeToString(v[:])
}

func rootFile(root string) *modfile.File {
	if _, err := os.Stat(filepath.Join(root, "cue.mod/local-module.cue")); !os.IsNotExist(err) {
		panic("local module replacements require additional integration")
	}
	mf := must(modfile.Parse(must(os.ReadFile(filepath.Join(root, "cue.mod/module.cue"))), "cue.mod/module.cue"))
	for _, dep := range mf.Deps {
		if dep.ReplaceWith != "" {
			panic("module replacements require additional integration")
		}
	}
	return mf
}

type Entry struct {
	Module         string                 `json:"module"`
	Version        string                 `json:"version"`
	Location       modconfig.HostLocation `json:"location"`
	Manifest       string                 `json:"manifest"`
	ManifestDigest string                 `json:"manifestDigest"`
	Extract        string                 `json:"extract"`
	Download       string                 `json:"download"`
}
type fixedResolver struct{ location modregistry.RegistryLocation }

func (r fixedResolver) ResolveToRegistry(string, string) (modregistry.RegistryLocation, error) {
	return r.location, nil
}

func unpack(entry Entry, zipData, modData []byte, out string) {
	var manifest struct {
		Layers []struct {
			Digest string `json:"digest"`
		} `json:"layers"`
	}
	check(json.Unmarshal([]byte(entry.Manifest), &manifest))
	if len(manifest.Layers) != 2 || digest(zipData) != manifest.Layers[0].Digest || digest(modData) != manifest.Layers[1].Digest || digest([]byte(entry.Manifest)) != entry.ManifestDigest {
		panic("native CUE cache differs from captured immutable OCI manifest")
	}
	mv := must(module.NewVersion(entry.Module, entry.Version))
	mf := must(modfile.Parse(modData, "module.cue"))
	if mf.QualifiedModule() != mv.Path() {
		panic("native module identity differs from manifest selection")
	}
	check(os.MkdirAll(out, 0755))
	check(os.WriteFile(filepath.Join(out, "archive.zip"), zipData, 0644))
	check(os.WriteFile(filepath.Join(out, "module.cue"), modData, 0644))
	check(modzip.Unzip(filepath.Join(out, "source"), mv, filepath.Join(out, "archive.zip")))
	sourceMod := must(os.ReadFile(filepath.Join(out, "source/cue.mod/module.cue")))
	if string(sourceMod) != string(modData) {
		panic("archive and native module metadata differ")
	}
}

func main() {
	defer func() {
		if failure := recover(); failure != nil {
			fmt.Fprintln(os.Stderr, "cue-purifier:", failure)
			os.Exit(1)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	switch os.Args[1] {
	case "graph":
		root := os.Args[2]
		mf := rootFile(root)
		registry := must(modconfig.NewRegistry(nil))
		requirements := modrequirements.NewRequirements(mf.QualifiedModule(), registry, mf.DepVersions(), mf.DefaultMajorVersions())
		graph := must(requirements.Graph(ctx))
		resolver := must(modconfig.NewResolver(nil))
		client := modregistry.NewClientWithResolver(resolver)
		entries := []Entry{}
		for _, mv := range graph.BuildList() {
			if mv.Version() == "" {
				continue
			}
			_ = must(registry.Fetch(ctx, mv))
			native := must(client.GetModule(ctx, mv))
			loc := must(resolver.ResolveToRegistry(mv.BasePath(), mv.Version()))
			reader := must(loc.Registry.GetManifest(ctx, loc.Repository, native.ManifestDigest()))
			manifest := must(io.ReadAll(reader))
			check(reader.Close())
			location, ok := resolver.ResolveToLocation(mv.BasePath(), mv.Version())
			if !ok {
				panic("missing registry location")
			}
			base := must(module.EscapePath(mv.BasePath()))
			version := must(module.EscapeVersion(mv.Version()))
			entries = append(entries, Entry{mv.Path(), mv.Version(), location, string(manifest), string(native.ManifestDigest()), "mod/extract/" + base + "@" + version, "mod/download/" + base + "/@v/" + version})
		}
		check(json.NewEncoder(os.Stdout).Encode(map[string]any{"native": mf, "entries": entries}))
	case "unpack":
		var entry Entry
		check(json.Unmarshal(must(os.ReadFile(os.Args[2])), &entry))
		unpack(entry, must(os.ReadFile(os.Args[3])), must(os.ReadFile(os.Args[4])), os.Args[5])
	case "inspect":
		check(json.NewEncoder(os.Stdout).Encode(rootFile(os.Args[2])))
	case "check":
		var expected struct {
			Native  any `json:"native"`
			Entries []struct {
				Cue Entry `json:"cue"`
			} `json:"entries"`
		}
		check(json.Unmarshal(must(os.ReadFile(os.Args[3])), &expected))
		mf := rootFile(os.Args[2])
		var actual any
		check(json.Unmarshal(must(json.Marshal(mf)), &actual))
		if !reflect.DeepEqual(actual, expected.Native) {
			panic("native CUE metadata differs from the lock")
		}
		registry := must(modconfig.NewRegistry(nil))
		graph := must(modrequirements.NewRequirements(mf.QualifiedModule(), registry, mf.DepVersions(), mf.DefaultMajorVersions()).Graph(ctx))
		selected := []string{}
		wanted := []string{}
		for _, mv := range graph.BuildList() {
			if mv.Version() != "" {
				selected = append(selected, mv.String())
			}
		}
		for _, record := range expected.Entries {
			entry := record.Cue
			mv := must(module.NewVersion(entry.Module, entry.Version))
			wanted = append(wanted, mv.String())
			base := must(module.EscapePath(mv.BasePath()))
			version := must(module.EscapeVersion(mv.Version()))
			if entry.Extract != "mod/extract/"+base+"@"+version || entry.Download != "mod/download/"+base+"/@v/"+version {
				panic("native CUE cache binding differs from the lock")
			}
		}
		if !bytes.Equal(must(json.Marshal(selected)), must(json.Marshal(wanted))) {
			panic("native CUE build list differs from the lock")
		}
	case "fetch":
		var entry Entry
		check(json.Unmarshal(must(os.ReadFile(os.Args[2])), &entry))
		host := entry.Location.Host
		if entry.Location.Insecure {
			host += "+insecure"
		}
		resolver := must(modconfig.NewResolver(&modconfig.Config{CUERegistry: host}))
		mv := must(module.NewVersion(entry.Module, entry.Version))
		loc := must(resolver.ResolveToRegistry(mv.BasePath(), entry.Version))
		loc.Repository = entry.Location.Repository
		client := modregistry.NewClientWithResolver(fixedResolver{loc})
		native := must(client.GetModuleWithManifest(mv, []byte(entry.Manifest), "application/vnd.oci.image.manifest.v1+json"))
		reader := must(native.GetZip(ctx))
		zipData := must(io.ReadAll(reader))
		check(reader.Close())
		modData := must(native.ModuleFile(ctx))
		unpack(entry, zipData, modData, os.Args[3])
	default:
		panic(fmt.Sprintf("unknown action %q", os.Args[1]))
	}
}
