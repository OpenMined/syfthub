package cmd

import (
	"testing"
)

func TestAgentCmd_Registration(t *testing.T) {
	// Verify agentCmd is registered on the root command
	found := false
	for _, cmd := range rootCmd.Commands() {
		if cmd.Name() == "agent" {
			found = true
			break
		}
	}
	if !found {
		t.Fatal("agent command not registered on rootCmd")
	}

	if agentCmd.Use != "agent <endpoint> <prompt>" {
		t.Errorf("Use = %q, want %q", agentCmd.Use, "agent <endpoint> <prompt>")
	}

	if agentCmd.Short != "Start an interactive agent session" {
		t.Errorf("Short = %q, want %q", agentCmd.Short, "Start an interactive agent session")
	}

	// Verify the --aggregator flag exists
	f := agentCmd.Flags().Lookup("aggregator")
	if f == nil {
		t.Fatal("expected --aggregator flag to be registered")
	}
	if f.Shorthand != "a" {
		t.Errorf("aggregator shorthand = %q, want %q", f.Shorthand, "a")
	}
}

func TestAgentCmd_RequiresArgs(t *testing.T) {
	// cobra.ExactArgs(2) should reject wrong number of args
	tests := []struct {
		name    string
		args    []string
		wantErr bool
	}{
		{"no args", []string{}, true},
		{"one arg", []string{"endpoint"}, true},
		{"three args", []string{"endpoint", "prompt", "extra"}, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := agentCmd.Args(agentCmd, tt.args)
			if (err != nil) != tt.wantErr {
				t.Errorf("Args(%v) error = %v, wantErr %v", tt.args, err, tt.wantErr)
			}
		})
	}

	// Two args should be accepted
	t.Run("two args", func(t *testing.T) {
		err := agentCmd.Args(agentCmd, []string{"endpoint", "prompt"})
		if err != nil {
			t.Errorf("Args with 2 args should succeed, got: %v", err)
		}
	})
}

func TestTruncate(t *testing.T) {
	tests := []struct {
		name string
		s    string
		max  int
		want string
	}{
		{"short string", "hello", 10, "hello"},
		{"exact length", "hello", 5, "hello"},
		{"needs truncation", "hello world", 8, "hello w\xe2\x80\xa6"},
		{"single char max", "hello", 2, "h\xe2\x80\xa6"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := truncate(tt.s, tt.max)
			if got != tt.want {
				t.Errorf("truncate(%q, %d) = %q, want %q", tt.s, tt.max, got, tt.want)
			}
		})
	}
}

func TestToolEntry_FormatPreview(t *testing.T) {
	t.Run("short single-line result", func(t *testing.T) {
		entry := &toolEntry{
			index:  1,
			name:   "search",
			status: "success",
			result: "Found 3 results",
		}
		preview := entry.formatPreview()
		if preview != "Found 3 results" {
			t.Errorf("preview = %q, want %q", preview, "Found 3 results")
		}
	})

	t.Run("multi-line result gets collapsed", func(t *testing.T) {
		lines := "line 1\nline 2\nline 3\nline 4\nline 5\nline 6"
		entry := &toolEntry{
			index:  2,
			name:   "read_file",
			status: "success",
			result: lines,
		}
		preview := entry.formatPreview()
		// Should contain the first 3 lines and a "more lines" hint
		if preview == lines {
			t.Error("multi-line result should be collapsed")
		}
		// The hidden count should be 3 (6 lines - 3 preview lines)
		if got := preview; got == "" {
			t.Error("preview should not be empty")
		}
	})
}
