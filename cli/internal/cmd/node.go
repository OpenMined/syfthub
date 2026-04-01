package cmd

import "github.com/spf13/cobra"

var nodeCmd = &cobra.Command{
	Use:   "node",
	Short: "Manage your SyftHub node",
	Long: `Manage a local SyftHub node that hosts endpoints.

A node runs endpoints locally and syncs them with SyftHub. Use 'syft node init'
to configure and start your node, then manage it with stop/status/logs.

Subcommands:
  init          Initialize and start the node daemon
  stop          Stop a running node
  status        Show node status
  logs          View node daemon logs
  endpoint      Manage local endpoints
  policy        Manage endpoint policies
`,
}

func init() {
	nodeCmd.AddCommand(nodeInitCmd)
	nodeCmd.AddCommand(nodeRunCmd)
	nodeCmd.AddCommand(nodeStopCmd)
	nodeCmd.AddCommand(nodeStatusCmd)
	nodeCmd.AddCommand(nodeLogsCmd)
	nodeCmd.AddCommand(nodeEndpointCmd)
	nodeCmd.AddCommand(nodePolicyCmd)
}
