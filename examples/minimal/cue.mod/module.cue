module: "purifier.example/proof@v0"
language: {
	version: "v0.17.0"
}
source: {
	kind: "self"
}
deps: {
	"cue.dev/x/k8s.io@v0": {
		v:       "v0.12.0"
		default: true
	}
}
