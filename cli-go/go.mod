module github.com/OpenMined/syfthub/cli-go

go 1.23.0

toolchain go1.24.1

require (
	github.com/fatih/color v1.16.0
	github.com/olekukonko/tablewriter v0.0.5
	github.com/openmined/syfthub/sdk/golang v0.0.0
	github.com/spf13/cobra v1.8.0
	golang.org/x/term v0.31.0
)

require (
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/mattn/go-colorable v0.1.13 // indirect
	github.com/mattn/go-isatty v0.0.20 // indirect
	github.com/mattn/go-runewidth v0.0.15 // indirect
	github.com/rivo/uniseg v0.4.4 // indirect
	github.com/spf13/pflag v1.0.5 // indirect
	golang.org/x/sys v0.32.0 // indirect
)

replace github.com/openmined/syfthub/sdk/golang => ../sdk/golang
