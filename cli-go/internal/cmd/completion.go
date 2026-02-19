package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/output"
)

var completionCmd = &cobra.Command{
	Use:   "completion",
	Short: "Generate shell completion scripts",
	Long:  `Generate shell completion scripts for bash, zsh, or fish.`,
}

var completionBashCmd = &cobra.Command{
	Use:   "bash",
	Short: "Generate Bash completion script",
	Long: `Generate Bash completion script.

Usage:
    syft completion bash >> ~/.bashrc
    # or
    syft completion bash > /etc/bash_completion.d/syft`,
	RunE: runCompletionBash,
}

var completionZshCmd = &cobra.Command{
	Use:   "zsh",
	Short: "Generate Zsh completion script",
	Long: `Generate Zsh completion script.

Usage:
    syft completion zsh >> ~/.zshrc
    # or
    syft completion zsh > ~/.zsh/completions/_syft`,
	RunE: runCompletionZsh,
}

var completionFishCmd = &cobra.Command{
	Use:   "fish",
	Short: "Generate Fish completion script",
	Long: `Generate Fish completion script.

Usage:
    syft completion fish > ~/.config/fish/completions/syft.fish`,
	RunE: runCompletionFish,
}

var completionInstallCmd = &cobra.Command{
	Use:   "install [shell]",
	Short: "Install shell completion for the current shell",
	Long: `Install shell completion for the current shell.

Detects the current shell and prints installation instructions.`,
	Args: cobra.MaximumNArgs(1),
	RunE: runCompletionInstall,
}

func init() {
	completionCmd.AddCommand(completionBashCmd)
	completionCmd.AddCommand(completionZshCmd)
	completionCmd.AddCommand(completionFishCmd)
	completionCmd.AddCommand(completionInstallCmd)
}

func runCompletionBash(cmd *cobra.Command, args []string) error {
	return rootCmd.GenBashCompletion(os.Stdout)
}

func runCompletionZsh(cmd *cobra.Command, args []string) error {
	return rootCmd.GenZshCompletion(os.Stdout)
}

func runCompletionFish(cmd *cobra.Command, args []string) error {
	return rootCmd.GenFishCompletion(os.Stdout, true)
}

func runCompletionInstall(cmd *cobra.Command, args []string) error {
	var shell string

	if len(args) > 0 {
		shell = args[0]
	} else {
		// Detect shell from environment
		shellPath := os.Getenv("SHELL")
		switch {
		case contains(shellPath, "bash"):
			shell = "bash"
		case contains(shellPath, "zsh"):
			shell = "zsh"
		case contains(shellPath, "fish"):
			shell = "fish"
		default:
			output.Error("Could not detect shell. Please specify: syft completion install bash|zsh|fish")
			return nil
		}
	}

	switch shell {
	case "bash":
		output.Cyan.Println("Bash completion installation:")
		fmt.Println()
		fmt.Println("Add to ~/.bashrc:")
		output.Dim.Println(`  eval "$(syft completion bash)"`)
		fmt.Println()
		fmt.Println("Or save to a file:")
		output.Dim.Println("  syft completion bash > ~/.bash_completions/syft.sh")
		output.Dim.Println(`  echo 'source ~/.bash_completions/syft.sh' >> ~/.bashrc`)

	case "zsh":
		output.Cyan.Println("Zsh completion installation:")
		fmt.Println()
		fmt.Println("Add to ~/.zshrc:")
		output.Dim.Println(`  eval "$(syft completion zsh)"`)
		fmt.Println()
		fmt.Println("Or save to completions directory:")
		output.Dim.Println("  syft completion zsh > ~/.zsh/completions/_syft")

	case "fish":
		output.Cyan.Println("Fish completion installation:")
		fmt.Println()
		fmt.Println("Save to completions directory:")
		output.Dim.Println("  syft completion fish > ~/.config/fish/completions/syft.fish")

	default:
		output.Error("Unknown shell: %s. Supported: bash, zsh, fish", shell)
		return nil
	}

	fmt.Println()
	output.Success("Run the command above to enable %s completion.", shell)

	return nil
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
