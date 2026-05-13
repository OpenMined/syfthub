package cmd

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// --- Parent command ---

var nodeEndpointSkillCmd = &cobra.Command{
	Use:     "skill",
	Aliases: []string{"skills"},
	Short:   "Manage SKILL.md files for an endpoint",
	Long: `Add, list, show, and remove SKILL.md files under an endpoint's
skills/ directory. Agent runners load these on startup; mutations trigger
an automatic reload via the node daemon's file watcher.`,
}

func init() {
	nodeEndpointSkillCmd.AddCommand(nodeEndpointSkillListCmd)
	nodeEndpointSkillCmd.AddCommand(nodeEndpointSkillShowCmd)
	nodeEndpointSkillCmd.AddCommand(nodeEndpointSkillAddCmd)
	nodeEndpointSkillCmd.AddCommand(nodeEndpointSkillRmCmd)
	nodeEndpointCmd.AddCommand(nodeEndpointSkillCmd)
}

// --- List ---

var nodeEPSkillListJSON bool

var nodeEndpointSkillListCmd = &cobra.Command{
	Use:   "list <endpoint-slug>",
	Short: "List skills for an endpoint",
	Args:  cobra.ExactArgs(1),
	RunE:  runNodeEndpointSkillList,
}

func init() {
	nodeEndpointSkillListCmd.Flags().BoolVar(&nodeEPSkillListJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointSkillList(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)

	skills, err := nodeops.ListSkills(endpointDir)
	if err != nil {
		output.ReplyErrorSoft(nodeEPSkillListJSON, "%v", err)
		return nil
	}

	if nodeEPSkillListJSON {
		entries := make([]map[string]any, 0, len(skills))
		for _, s := range skills {
			entries = append(entries, map[string]any{
				"name":       s.Name,
				"title":      s.Title,
				"size":       s.Size,
				"modifiedAt": s.ModifiedAt.Format(time.RFC3339),
			})
		}
		output.JSON(map[string]any{
			"status": output.StatusSuccess,
			"slug":   slug,
			"skills": entries,
		})
		return nil
	}

	if len(skills) == 0 {
		fmt.Printf("No skills installed for endpoint '%s'.\n", slug)
		fmt.Printf("Add one with: syft node endpoint skill add %s <name> --file <path>\n", slug)
		return nil
	}

	table := output.Table([]string{"NAME", "TITLE", "SIZE", "MODIFIED"})
	for _, s := range skills {
		table.Append([]string{
			s.Name,
			s.Title,
			fmt.Sprintf("%d", s.Size),
			s.ModifiedAt.Format(time.RFC3339),
		})
	}
	table.Render()
	return nil
}

// --- Show ---

var nodeEPSkillShowJSON bool

var nodeEndpointSkillShowCmd = &cobra.Command{
	Use:   "show <endpoint-slug> <skill-name>",
	Short: "Print a skill's SKILL.md body",
	Args:  cobra.ExactArgs(2),
	RunE:  runNodeEndpointSkillShow,
}

func init() {
	nodeEndpointSkillShowCmd.Flags().BoolVar(&nodeEPSkillShowJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointSkillShow(cmd *cobra.Command, args []string) error {
	slug, name := args[0], args[1]
	cfg := nodeconfig.Load()
	body, err := nodeops.ReadSkill(filepath.Join(cfg.EndpointsPath, slug), name)
	if err != nil {
		output.ReplyErrorSoft(nodeEPSkillShowJSON, "%v", err)
		return nil
	}
	if nodeEPSkillShowJSON {
		output.JSON(map[string]any{
			"status": output.StatusSuccess,
			"slug":   slug,
			"name":   name,
			"body":   body,
		})
		return nil
	}
	fmt.Print(body)
	if !strings.HasSuffix(body, "\n") {
		fmt.Println()
	}
	return nil
}

// --- Add ---

var (
	nodeEPSkillAddFile  string
	nodeEPSkillAddStdin bool
	nodeEPSkillAddForce bool
	nodeEPSkillAddJSON  bool
)

var nodeEndpointSkillAddCmd = &cobra.Command{
	Use:   "add <endpoint-slug> <skill-name>",
	Short: "Add or update a skill",
	Long: `Create or replace <endpoints>/<slug>/skills/<skill-name>/SKILL.md.

The skill body is read from --file, from stdin (--stdin), or — if
neither is given — from stdin when piped. Skill name must match
^[a-z0-9][a-z0-9_-]{0,63}$.`,
	Args: cobra.ExactArgs(2),
	RunE: runNodeEndpointSkillAdd,
}

func init() {
	nodeEndpointSkillAddCmd.Flags().StringVarP(&nodeEPSkillAddFile, "file", "f", "", "Read skill body from this file")
	nodeEndpointSkillAddCmd.Flags().BoolVar(&nodeEPSkillAddStdin, "stdin", false, "Read skill body from stdin")
	nodeEndpointSkillAddCmd.Flags().BoolVar(&nodeEPSkillAddForce, "force", false, "Overwrite without confirmation")
	nodeEndpointSkillAddCmd.Flags().BoolVar(&nodeEPSkillAddJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointSkillAdd(cmd *cobra.Command, args []string) error {
	slug, name := args[0], args[1]
	cfg := nodeconfig.Load()
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)

	body, err := readSkillBody(nodeEPSkillAddFile, nodeEPSkillAddStdin)
	if err != nil {
		output.ReplyErrorSoft(nodeEPSkillAddJSON, "%v", err)
		return nil
	}

	// Confirm overwrite when interactive and not forced.
	skillPath := filepath.Join(endpointDir, nodeops.SkillsDirName, name, nodeops.SkillFileName)
	if _, statErr := os.Stat(skillPath); statErr == nil && !nodeEPSkillAddForce && term.IsTerminal(int(os.Stdin.Fd())) {
		fmt.Printf("Skill '%s' already exists for endpoint '%s'. Overwrite? [y/N]: ", name, slug)
		var confirm string
		fmt.Scanln(&confirm)
		if strings.ToLower(confirm) != "y" {
			fmt.Println("Cancelled.")
			return nil
		}
	}

	if err := nodeops.WriteSkill(endpointDir, name, body); err != nil {
		output.ReplyErrorSoft(nodeEPSkillAddJSON, "%v", err)
		return nil
	}

	if nodeEPSkillAddJSON {
		output.JSON(map[string]any{
			"status": output.StatusSuccess,
			"slug":   slug,
			"skill":  name,
			"path":   skillPath,
		})
	} else {
		output.Success("Added skill '%s' to endpoint '%s'.", name, slug)
		fmt.Printf("  Path: %s\n", skillPath)
	}
	return nil
}

// readSkillBody resolves the skill body from --file, stdin, or piped input.
func readSkillBody(file string, stdinFlag bool) (string, error) {
	if file != "" && stdinFlag {
		return "", fmt.Errorf("--file and --stdin are mutually exclusive")
	}
	if file != "" {
		b, err := os.ReadFile(file)
		if err != nil {
			return "", fmt.Errorf("read %s: %w", file, err)
		}
		return string(b), nil
	}

	// Read from stdin if requested explicitly or if input is piped.
	piped := !term.IsTerminal(int(os.Stdin.Fd()))
	if !stdinFlag && !piped {
		return "", fmt.Errorf("no skill body provided: use --file <path> or pipe content via stdin")
	}
	b, err := io.ReadAll(os.Stdin)
	if err != nil {
		return "", fmt.Errorf("read stdin: %w", err)
	}
	if strings.TrimSpace(string(b)) == "" {
		return "", fmt.Errorf("skill body from stdin is empty")
	}
	return string(b), nil
}

// --- Remove ---

var (
	nodeEPSkillRmForce bool
	nodeEPSkillRmJSON  bool
)

var nodeEndpointSkillRmCmd = &cobra.Command{
	Use:     "rm <endpoint-slug> <skill-name>",
	Aliases: []string{"remove", "delete"},
	Short:   "Remove a skill",
	Args:    cobra.ExactArgs(2),
	RunE:    runNodeEndpointSkillRm,
}

func init() {
	nodeEndpointSkillRmCmd.Flags().BoolVar(&nodeEPSkillRmForce, "force", false, "Skip confirmation prompt")
	nodeEndpointSkillRmCmd.Flags().BoolVar(&nodeEPSkillRmJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointSkillRm(cmd *cobra.Command, args []string) error {
	slug, name := args[0], args[1]
	cfg := nodeconfig.Load()
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)

	if !nodeEPSkillRmForce && term.IsTerminal(int(os.Stdin.Fd())) {
		fmt.Printf("Remove skill '%s' from endpoint '%s'? [y/N]: ", name, slug)
		var confirm string
		fmt.Scanln(&confirm)
		if strings.ToLower(confirm) != "y" {
			fmt.Println("Cancelled.")
			return nil
		}
	}

	if err := nodeops.RemoveSkill(endpointDir, name); err != nil {
		output.ReplyErrorSoft(nodeEPSkillRmJSON, "%v", err)
		return nil
	}

	if nodeEPSkillRmJSON {
		output.JSON(map[string]any{"status": output.StatusSuccess, "slug": slug, "skill": name})
	} else {
		output.Success("Removed skill '%s' from endpoint '%s'.", name, slug)
	}
	return nil
}
