package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// --- Parent command ---

var nodePolicyCmd = &cobra.Command{
	Use:   "policy",
	Short: "Manage endpoint policies",
	Long:  `Add, list, and remove policies from endpoint policies.yaml files.`,
}

func init() {
	nodePolicyCmd.AddCommand(nodePolicyAddCmd)
	nodePolicyCmd.AddCommand(nodePolicyListCmd)
	nodePolicyCmd.AddCommand(nodePolicyRemoveCmd)
}

// --- Add ---

var (
	nodePolicyAddName   string
	nodePolicyAddType   string
	nodePolicyAddConfig []string
	nodePolicyAddJSON   bool
)

var nodePolicyAddCmd = &cobra.Command{
	Use:   "add <endpoint-slug>",
	Short: "Add a policy to an endpoint",
	Long:  `Add or update a policy in an endpoint's policies.yaml.`,
	Args:  cobra.ExactArgs(1),
	RunE:  runNodePolicyAdd,
}

func init() {
	nodePolicyAddCmd.Flags().StringVar(&nodePolicyAddName, "name", "", "Policy name (required)")
	nodePolicyAddCmd.Flags().StringVar(&nodePolicyAddType, "type", "", "Policy type (required)")
	nodePolicyAddCmd.Flags().StringSliceVar(&nodePolicyAddConfig, "config", nil, "Config key=value pairs (repeatable; ignored for --type transaction)")
	nodePolicyAddCmd.Flags().BoolVar(&nodePolicyAddJSON, "json", false, "Output result as JSON")
	nodePolicyAddCmd.MarkFlagRequired("name")
	nodePolicyAddCmd.MarkFlagRequired("type")

	// Transaction policies use a dedicated set of flags and write a per-policy
	// YAML + HMAC secret instead of appending to policies.yaml.
	registerTransactionPolicyFlags(nodePolicyAddCmd)
}

func runNodePolicyAdd(cmd *cobra.Command, args []string) error {
	slug := args[0]

	// Transaction policies have their own validation, file layout, and side
	// effects (HMAC secret + .gitignore). Dispatch early so the legacy
	// policies.yaml path stays untouched for non-transaction types.
	if nodePolicyAddType == PolicyTypeTransaction {
		return runNodePolicyAddTransaction(slug)
	}

	cfg := nodeconfig.Load()

	// Parse config key=value pairs
	configMap := make(map[string]any)
	for _, kv := range nodePolicyAddConfig {
		parts := strings.SplitN(kv, "=", 2)
		if len(parts) != 2 {
			output.ReplyErrorSoft(nodePolicyAddJSON, "Invalid config format: %q (expected key=value)", kv)
			return nil
		}
		configMap[parts[0]] = parts[1]
	}

	policy := nodeops.Policy{
		Name:   nodePolicyAddName,
		Type:   nodePolicyAddType,
		Config: configMap,
	}

	policiesPath := filepath.Join(cfg.EndpointsPath, slug, "policies.yaml")
	if err := nodeops.SavePolicy(policiesPath, policy); err != nil {
		output.ReplyErrorSoft(nodePolicyAddJSON, "%v", err)
		return nil
	}

	if nodePolicyAddJSON {
		output.JSON(map[string]any{
			"status": output.StatusSuccess,
			"slug":   slug,
			"policy": nodePolicyAddName,
		})
	} else {
		output.Success("Added policy '%s' (%s) to endpoint '%s'.", nodePolicyAddName, nodePolicyAddType, slug)
	}
	return nil
}

// runNodePolicyAddTransaction is the cobra-side entry point for the
// `--type transaction` branch. It glues the flag values onto the
// implementation in node_policy_transaction.go and produces the JSON / human
// output. Kept here (next to runNodePolicyAdd) so the dispatch is colocated
// with the rest of the policy-add flow.
func runNodePolicyAddTransaction(slug string) error {
	endpointDir := resolveTransactionEndpointDir(slug)
	args := transactionArgsFromFlags()

	outcome, err := runTransactionPolicyAdd(endpointDir, args)
	if err != nil {
		output.ReplyErrorSoft(nodePolicyAddJSON, "%v", err)
		return nil
	}

	if nodePolicyAddJSON {
		output.JSON(map[string]any{
			"status":            output.StatusSuccess,
			"slug":              slug,
			"policy":            nodePolicyAddName,
			"type":              PolicyTypeTransaction,
			"policy_path":       outcome.PolicyPath,
			"secret_path":       outcome.SecretPath,
			"gitignore_updated": outcome.GitignoreUpdated,
		})
		return nil
	}

	printTransactionPolicySuccess(slug, outcome)
	return nil
}

// --- List ---

var nodePolicyListJSON bool

var nodePolicyListCmd = &cobra.Command{
	Use:   "list <endpoint-slug>",
	Short: "List policies for an endpoint",
	Long:  `Display all policies configured in an endpoint's policies.yaml.`,
	Args:  cobra.ExactArgs(1),
	RunE:  runNodePolicyList,
}

func init() {
	nodePolicyListCmd.Flags().BoolVar(&nodePolicyListJSON, "json", false, "Output result as JSON")
}

func runNodePolicyList(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()

	policiesPath := filepath.Join(cfg.EndpointsPath, slug, "policies.yaml")
	policies, err := nodeops.GetPolicies(policiesPath)
	if err != nil {
		output.ReplyErrorSoft(nodePolicyListJSON, "%v", err)
		return nil
	}

	if nodePolicyListJSON {
		output.JSON(map[string]any{"status": output.StatusSuccess, "slug": slug, "policies": policies})
		return nil
	}

	if len(policies) == 0 {
		fmt.Printf("No policies configured for endpoint '%s'.\n", slug)
		return nil
	}

	table := output.Table([]string{"NAME", "TYPE", "CONFIG KEYS"})
	for _, p := range policies {
		keys := make([]string, 0, len(p.Config))
		for k := range p.Config {
			keys = append(keys, k)
		}
		table.Append([]string{
			p.Name,
			p.Type,
			strings.Join(keys, ", "),
		})
	}
	table.Render()

	return nil
}

// --- Remove ---

var (
	nodePolicyRemoveName  string
	nodePolicyRemoveForce bool
	nodePolicyRemoveJSON  bool
)

var nodePolicyRemoveCmd = &cobra.Command{
	Use:   "remove <endpoint-slug>",
	Short: "Remove a policy from an endpoint",
	Long:  `Remove a policy by name from an endpoint's policies.yaml.`,
	Args:  cobra.ExactArgs(1),
	RunE:  runNodePolicyRemove,
}

func init() {
	nodePolicyRemoveCmd.Flags().StringVar(&nodePolicyRemoveName, "name", "", "Policy name to remove (required)")
	nodePolicyRemoveCmd.Flags().BoolVar(&nodePolicyRemoveForce, "force", false, "Skip confirmation prompt")
	nodePolicyRemoveCmd.Flags().BoolVar(&nodePolicyRemoveJSON, "json", false, "Output result as JSON")
	nodePolicyRemoveCmd.MarkFlagRequired("name")
}

func runNodePolicyRemove(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()

	if !nodePolicyRemoveForce && term.IsTerminal(int(os.Stdin.Fd())) {
		fmt.Printf("Remove policy '%s' from endpoint '%s'? [y/N]: ", nodePolicyRemoveName, slug)
		var confirm string
		fmt.Scanln(&confirm)
		if strings.ToLower(confirm) != "y" {
			fmt.Println("Cancelled.")
			return nil
		}
	}

	policiesPath := filepath.Join(cfg.EndpointsPath, slug, "policies.yaml")
	if err := nodeops.DeletePolicy(policiesPath, nodePolicyRemoveName); err != nil {
		output.ReplyErrorSoft(nodePolicyRemoveJSON, "%v", err)
		return nil
	}

	if nodePolicyRemoveJSON {
		output.JSON(map[string]any{"status": output.StatusSuccess, "slug": slug, "policy": nodePolicyRemoveName})
	} else {
		output.Success("Removed policy '%s' from endpoint '%s'.", nodePolicyRemoveName, slug)
	}
	return nil
}
