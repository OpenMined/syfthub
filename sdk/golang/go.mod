module github.com/openmined/syfthub/sdk/golang

go 1.25.0

require (
	github.com/ethereum/go-ethereum v1.14.11
	github.com/fsnotify/fsnotify v1.7.0
	github.com/google/uuid v1.6.0
	github.com/modelcontextprotocol/go-sdk v1.6.1
	github.com/nats-io/nats-server/v2 v2.10.22
	github.com/nats-io/nats.go v1.48.0
	github.com/openmined/syfthub/sdk/golang/mppx v0.0.0-00010101000000-000000000000
	golang.org/x/crypto v0.45.0
	golang.org/x/oauth2 v0.35.0
	golang.org/x/sync v0.7.0
	gopkg.in/yaml.v3 v3.0.1
)

replace github.com/openmined/syfthub/sdk/golang/mppx => ./mppx

require (
	github.com/bits-and-blooms/bitset v1.13.0 // indirect
	github.com/btcsuite/btcd/btcec/v2 v2.3.4 // indirect
	github.com/consensys/bavard v0.1.13 // indirect
	github.com/consensys/gnark-crypto v0.12.1 // indirect
	github.com/crate-crypto/go-ipa v0.0.0-20240223125850-b1e8a79f509c // indirect
	github.com/crate-crypto/go-kzg-4844 v1.0.0 // indirect
	github.com/decred/dcrd/dcrec/secp256k1/v4 v4.0.1 // indirect
	github.com/ethereum/c-kzg-4844 v1.0.0 // indirect
	github.com/ethereum/go-verkle v0.1.1-0.20240829091221-dffa7562dbe9 // indirect
	github.com/google/jsonschema-go v0.4.3 // indirect
	github.com/holiman/uint256 v1.3.1 // indirect
	github.com/klauspost/compress v1.18.0 // indirect
	github.com/minio/highwayhash v1.0.3 // indirect
	github.com/mmcloughlin/addchain v0.4.0 // indirect
	github.com/nats-io/jwt/v2 v2.5.8 // indirect
	github.com/nats-io/nkeys v0.4.11 // indirect
	github.com/nats-io/nuid v1.0.1 // indirect
	github.com/segmentio/asm v1.1.3 // indirect
	github.com/segmentio/encoding v0.5.4 // indirect
	github.com/supranational/blst v0.3.13 // indirect
	github.com/yosida95/uritemplate/v3 v3.0.2 // indirect
	golang.org/x/sys v0.41.0 // indirect
	golang.org/x/time v0.7.0 // indirect
	rsc.io/tmplfunc v0.0.3 // indirect
)
