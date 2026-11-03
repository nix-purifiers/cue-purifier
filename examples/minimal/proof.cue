package proof

import core "cue.dev/x/k8s.io/api/core/v1"

answer: 42
service: core.#Service & {
    metadata: name: "purifier-proof"
    spec: {
        ports: [{port: 42}]
        selector: app: "proof"
    }
}
