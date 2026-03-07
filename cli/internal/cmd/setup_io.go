package cmd

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"syscall"

	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// CLISetupIO implements setupflow.SetupIO for terminal interaction.
type CLISetupIO struct {
	reader *bufio.Reader
}

// NewCLISetupIO creates a new CLISetupIO.
func NewCLISetupIO() *CLISetupIO {
	return &CLISetupIO{reader: bufio.NewReader(os.Stdin)}
}

func (io *CLISetupIO) Prompt(message string, opts setupflow.PromptOpts) (string, error) {
	if opts.Secret {
		// Show prompt with default indicator
		if opts.Default != "" {
			fmt.Printf("  %s [****]: ", message)
		} else {
			fmt.Printf("  %s: ", message)
		}
		byteVal, err := term.ReadPassword(int(syscall.Stdin))
		fmt.Println()
		if err != nil {
			return "", fmt.Errorf("failed to read input: %w", err)
		}
		return strings.TrimSpace(string(byteVal)), nil
	}

	// Non-secret prompt
	if opts.Default != "" {
		fmt.Printf("  %s [%s]: ", message, opts.Default)
	} else {
		fmt.Printf("  %s: ", message)
	}
	line, err := io.reader.ReadString('\n')
	if err != nil {
		return "", fmt.Errorf("failed to read input: %w", err)
	}
	return strings.TrimSpace(line), nil
}

func (io *CLISetupIO) Select(message string, options []setupflow.SelectOption) (string, error) {
	fmt.Printf("\n  %s\n\n", message)
	for i, opt := range options {
		fmt.Printf("    %d) %s", i+1, opt.Label)
		if opt.Value != opt.Label {
			fmt.Printf(" (%s)", opt.Value)
		}
		fmt.Println()
	}
	fmt.Println()

	for {
		fmt.Printf("  Enter choice [1-%d]: ", len(options))
		line, err := io.reader.ReadString('\n')
		if err != nil {
			return "", fmt.Errorf("failed to read input: %w", err)
		}
		choice := strings.TrimSpace(line)
		idx, err := strconv.Atoi(choice)
		if err != nil || idx < 1 || idx > len(options) {
			fmt.Printf("  Please enter a number between 1 and %d.\n", len(options))
			continue
		}
		return options[idx-1].Value, nil
	}
}

func (io *CLISetupIO) Confirm(message string) (bool, error) {
	fmt.Printf("  %s [y/N]: ", message)
	line, err := io.reader.ReadString('\n')
	if err != nil {
		return false, fmt.Errorf("failed to read input: %w", err)
	}
	response := strings.TrimSpace(strings.ToLower(line))
	return response == "y" || response == "yes", nil
}

func (io *CLISetupIO) OpenBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "windows":
		cmd = exec.Command("cmd", "/c", "start", url)
	default: // linux and others
		cmd = exec.Command("xdg-open", url)
	}
	return cmd.Start()
}

func (io *CLISetupIO) Status(message string) {
	output.Info(message)
}

func (io *CLISetupIO) Error(message string) {
	output.Error(message)
}
