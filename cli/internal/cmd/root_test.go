package cmd

import (
	"testing"

	"github.com/spf13/cobra"
)

func TestIsAuthExempt(t *testing.T) {
	t.Run("command with annotation is exempt", func(t *testing.T) {
		cmd := &cobra.Command{
			Use:         "test",
			Annotations: map[string]string{authExemptKey: "true"},
		}
		if !isAuthExempt(cmd) {
			t.Error("expected command with auth-exempt annotation to be exempt")
		}
	})

	t.Run("command without annotation is not exempt", func(t *testing.T) {
		cmd := &cobra.Command{
			Use: "test",
		}
		if isAuthExempt(cmd) {
			t.Error("expected command without annotation to not be exempt")
		}
	})

	t.Run("child inherits parent annotation", func(t *testing.T) {
		parent := &cobra.Command{
			Use:         "parent",
			Annotations: map[string]string{authExemptKey: "true"},
		}
		child := &cobra.Command{
			Use: "child",
		}
		parent.AddCommand(child)

		if !isAuthExempt(child) {
			t.Error("expected child to inherit auth-exempt from parent")
		}
	})

	t.Run("child without parent annotation is not exempt", func(t *testing.T) {
		parent := &cobra.Command{
			Use: "parent",
		}
		child := &cobra.Command{
			Use: "child",
		}
		parent.AddCommand(child)

		if isAuthExempt(child) {
			t.Error("expected child without exempt parent to not be exempt")
		}
	})

	t.Run("deeply nested child inherits ancestor annotation", func(t *testing.T) {
		grandparent := &cobra.Command{
			Use:         "grandparent",
			Annotations: map[string]string{authExemptKey: "true"},
		}
		parent := &cobra.Command{
			Use: "parent",
		}
		child := &cobra.Command{
			Use: "child",
		}
		grandparent.AddCommand(parent)
		parent.AddCommand(child)

		if !isAuthExempt(child) {
			t.Error("expected deeply nested child to inherit auth-exempt from grandparent")
		}
	})

	t.Run("annotation value must be 'true'", func(t *testing.T) {
		cmd := &cobra.Command{
			Use:         "test",
			Annotations: map[string]string{authExemptKey: "false"},
		}
		if isAuthExempt(cmd) {
			t.Error("expected annotation value 'false' to not be exempt")
		}
	})
}

func TestKnownExemptCommands(t *testing.T) {
	// Verify that specific commands we know should be exempt are actually exempt.
	exemptNames := []string{"login", "logout", "upgrade", "completion", "config"}

	for _, name := range exemptNames {
		t.Run(name, func(t *testing.T) {
			var found *cobra.Command
			for _, cmd := range rootCmd.Commands() {
				if cmd.Name() == name {
					found = cmd
					break
				}
			}
			if found == nil {
				t.Skipf("command %q not found on rootCmd", name)
				return
			}
			if !isAuthExempt(found) {
				t.Errorf("command %q should be auth-exempt", name)
			}
		})
	}
}

func TestKnownNonExemptCommands(t *testing.T) {
	// Commands that require authentication should not be exempt.
	nonExemptNames := []string{"agent", "query", "ls", "whoami"}

	for _, name := range nonExemptNames {
		t.Run(name, func(t *testing.T) {
			var found *cobra.Command
			for _, cmd := range rootCmd.Commands() {
				if cmd.Name() == name {
					found = cmd
					break
				}
			}
			if found == nil {
				t.Skipf("command %q not found on rootCmd", name)
				return
			}
			if isAuthExempt(found) {
				t.Errorf("command %q should NOT be auth-exempt", name)
			}
		})
	}
}

func TestEnsureAuthenticated_SkipsExemptCommands(t *testing.T) {
	cmd := &cobra.Command{
		Use:         "test-exempt",
		Annotations: map[string]string{authExemptKey: "true"},
	}

	// ensureAuthenticated should return nil for exempt commands without
	// trying to load config or open a browser.
	err := ensureAuthenticated(cmd, nil)
	if err != nil {
		t.Errorf("ensureAuthenticated should return nil for exempt command, got: %v", err)
	}
}

func TestEnsureAuthenticated_SkipsWhenAPIKeyFlagChanged(t *testing.T) {
	cmd := &cobra.Command{
		Use: "test-apikey",
	}
	cmd.Flags().String("api-key", "", "API key")
	// Simulate the flag being set by the user
	cmd.Flags().Set("api-key", "my-token")

	err := ensureAuthenticated(cmd, nil)
	if err != nil {
		t.Errorf("ensureAuthenticated should return nil when --api-key flag is set, got: %v", err)
	}
}

func TestEnsureAuthenticated_NonInteractiveSkipsBrowser(t *testing.T) {
	// In a test environment, stdin is not a terminal. ensureAuthenticated
	// should return nil (skip browser) for a non-exempt command without a
	// token, letting the command produce its own auth error.
	cmd := &cobra.Command{
		Use: "test-noauth",
	}

	// No api-key flag, not exempt, no token in config, not a terminal.
	err := ensureAuthenticated(cmd, nil)
	if err != nil {
		t.Errorf("ensureAuthenticated should return nil in non-interactive environment, got: %v", err)
	}
}
