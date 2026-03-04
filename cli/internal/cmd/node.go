package cmd

import "github.com/spf13/cobra"

var nodeCmd = &cobra.Command{
	Use:   "node",
	Short: "Manage your SyftHub node",
	Long: `Manage a local SyftHub node that hosts endpoints.

A node runs endpoints locally and syncs them with SyftHub. Use 'syft node init'
to configure your node, then 'syft node start' to bring it online.

Subcommands:
  init          Initialize node configuration
  start         Start the node server
  stop          Stop a running node
  status        Show node status
  endpoint      Manage local endpoints
  policy        Manage endpoint policies
  marketplace   Browse and install marketplace packages`,
}

func init() {
	nodeCmd.AddCommand(nodeInitCmd)
	nodeCmd.AddCommand(nodeStartCmd)
	nodeCmd.AddCommand(nodeStopCmd)
	nodeCmd.AddCommand(nodeStatusCmd)
	nodeCmd.AddCommand(nodeEndpointCmd)
	nodeCmd.AddCommand(nodePolicyCmd)
	nodeCmd.AddCommand(nodeMarketplaceCmd)
}
