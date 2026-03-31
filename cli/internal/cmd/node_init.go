package cmd

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/charmbracelet/huh"
	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow/handlers"
)

var (
	nodeInitHubURL        string
	nodeInitAPIKey        string
	nodeInitEndpointsPath string
	nodeInitPort          int
	nodeInitForce         bool
	nodeInitJSON          bool
	nodeInitContainer     bool
)

var nodeInitCmd = &cobra.Command{
	Use:   "init",
	Short: "Initialize and start the node daemon",
	Long: `Initialize the SyftHub node configuration and start it as a background daemon.

Creates the shared configuration at ~/.config/syfthub/settings.json (the same
config used by syfthub-desktop). If no flags are provided and stdin is a
terminal, prompts interactively for required values.

The node always uses NATS tunneling mode (like syfthub-desktop). The tunnel
username is derived automatically from your API key at startup.

If a node is already running, use --force to reinitialize and restart it.`,
	RunE: runNodeInit,
}

func init() {
	nodeInitCmd.Flags().StringVar(&nodeInitHubURL, "hub-url", "", "SyftHub URL")
	nodeInitCmd.Flags().StringVar(&nodeInitAPIKey, "api-key", "", "API key or PAT")
	nodeInitCmd.Flags().StringVar(&nodeInitEndpointsPath, "endpoints-path", "", "Path to endpoints directory")
	nodeInitCmd.Flags().IntVar(&nodeInitPort, "port", 0, "HTTP server port")
	nodeInitCmd.Flags().BoolVar(&nodeInitForce, "force", false, "Overwrite existing configuration and restart")
	nodeInitCmd.Flags().BoolVar(&nodeInitJSON, "json", false, "Output result as JSON")
	nodeInitCmd.Flags().BoolVar(&nodeInitContainer, "container", false, "Enable container mode (run endpoints in Docker/Podman containers)")
}

func runNodeInit(cmd *cobra.Command, args []string) error {
	// Check if already initialized
	existing := nodeconfig.Load()
	if existing.Configured() && !nodeInitForce {
		alreadyRunning := false
		if p, err := nodeconfig.ReadPID(); err == nil {
			if proc, err := os.FindProcess(p); err == nil {
				if proc.Signal(syscall.Signal(0)) == nil {
					alreadyRunning = true
				}
			}
		}

		if alreadyRunning {
			if nodeInitJSON {
				output.JSON(map[string]any{
					"status":  "error",
					"message": "Node is already configured and running. Use --force to reinitialize.",
					"path":    nodeconfig.ConfigFile,
				})
			} else {
				output.Warning("Node is already configured and running at %s", nodeconfig.ConfigFile)
				output.Info("Use --force to reinitialize.")
			}
			return nil
		}

		// Configured but not running — start with existing config
		if !nodeInitJSON {
			output.Info("Node is configured but not running. Starting daemon...")
		}
		daemonPID, err := startNodeDaemon()
		if err != nil {
			if nodeInitJSON {
				output.JSON(map[string]any{
					"status":  "error",
					"message": fmt.Sprintf("Failed to start daemon: %v", err),
				})
			} else {
				output.Error("Failed to start daemon: %v", err)
				fmt.Println("  You can try starting manually with 'syft node run'")
			}
			return err
		}
		if nodeInitJSON {
			output.JSON(map[string]any{
				"status":         "success",
				"config_path":    nodeconfig.ConfigFile,
				"endpoints_path": existing.EndpointsPath,
				"syfthub_url":    existing.HubURL,
				"port":           existing.Port,
				"pid":            daemonPID,
			})
		} else {
			output.Success("Node started!")
			fmt.Printf("  Config:    %s\n", nodeconfig.ConfigFile)
			fmt.Printf("  Endpoints: %s\n", existing.EndpointsPath)
			fmt.Printf("  Hub URL:   %s\n", existing.HubURL)
			fmt.Printf("  Port:      %d\n", existing.Port)
			fmt.Printf("  PID:       %d\n", daemonPID)
			fmt.Printf("  Logs:      %s\n", nodeconfig.LogFile)
		}
		return nil
	}

	// If forcing and a node is running, stop it first
	if nodeInitForce {
		stopExistingNode()
	}

	cfgCopy := *existing
	cfg := &cfgCopy
	cfg.IsConfigured = false

	// Apply flag overrides
	if nodeInitHubURL != "" {
		cfg.HubURL = nodeInitHubURL
	}
	if nodeInitAPIKey != "" {
		cfg.APIToken = nodeInitAPIKey
	}
	if nodeInitEndpointsPath != "" {
		cfg.EndpointsPath = nodeInitEndpointsPath
	}
	if nodeInitPort > 0 {
		cfg.Port = nodeInitPort
	}
	if nodeInitContainer {
		cfg.ContainerEnabled = true
	}

	// Interactive prompting for API token if missing
	if term.IsTerminal(int(os.Stdin.Fd())) {
		reader := bufio.NewReader(os.Stdin)
		if cfg.APIToken == "" {
			cfg.APIToken = promptRequired(reader, "API Key (PAT)")
		}
	}

	cfg.IsConfigured = true

	if err := nodeconfig.EnsureConfigDir(); err != nil {
		if nodeInitJSON {
			output.JSON(map[string]any{"status": "error", "message": err.Error()})
		} else {
			output.Error("Failed to create config directory: %v", err)
		}
		return err
	}

	if err := os.MkdirAll(cfg.EndpointsPath, 0755); err != nil {
		if nodeInitJSON {
			output.JSON(map[string]any{"status": "error", "message": err.Error()})
		} else {
			output.Error("Failed to create endpoints directory: %v", err)
		}
		return err
	}

	if !nodeInitJSON {
		promptEndpointSetup(cfg)
	}

	if err := cfg.Save(); err != nil {
		if nodeInitJSON {
			output.JSON(map[string]any{"status": "error", "message": err.Error()})
		} else {
			output.Error("Failed to save configuration: %v", err)
		}
		return err
	}

	daemonPID, err := startNodeDaemon()
	if err != nil {
		if nodeInitJSON {
			output.JSON(map[string]any{
				"status":  "error",
				"message": fmt.Sprintf("Config saved but failed to start daemon: %v", err),
			})
		} else {
			output.Error("Config saved but failed to start daemon: %v", err)
			fmt.Printf("  Config: %s\n", nodeconfig.ConfigFile)
			fmt.Println("  You can try starting manually with 'syft node run'")
		}
		return err
	}

	if nodeInitJSON {
		output.JSON(map[string]any{
			"status":         "success",
			"config_path":    nodeconfig.ConfigFile,
			"endpoints_path": cfg.EndpointsPath,
			"syfthub_url":    cfg.HubURL,
			"port":           cfg.Port,
			"pid":            daemonPID,
		})
	} else {
		output.Success("Node initialized and started!")
		fmt.Printf("  Config:    %s\n", nodeconfig.ConfigFile)
		fmt.Printf("  Endpoints: %s\n", cfg.EndpointsPath)
		fmt.Printf("  Hub URL:   %s\n", cfg.HubURL)
		fmt.Printf("  Port:      %d\n", cfg.Port)
		fmt.Printf("  PID:       %d\n", daemonPID)
		fmt.Printf("  Logs:      %s\n", nodeconfig.LogFile)
		fmt.Println()
		fmt.Println("Use 'syft node logs -f' to follow daemon output.")
		fmt.Println("Use 'syft node stop' to stop the daemon.")
	}

	return nil
}

// pkgDisplayType returns the display type for a marketplace package.
// Packages tagged "agent" are shown as the "agent" type even when their
// stored marketplace type is "model" (the schema only has model/data_source).
func pkgDisplayType(pkg nodeops.MarketplacePackage) string {
	if slices.Contains(pkg.Tags, "agent") {
		return "agent"
	}
	return pkg.Type
}

// promptEndpointSetup presents an interactive marketplace picker when the
// endpoints directory is empty. No-op in non-TTY environments or when
// endpoints already exist.
func promptEndpointSetup(cfg *nodeconfig.NodeConfig) {
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		return
	}
	entries, err := os.ReadDir(cfg.EndpointsPath)
	if err != nil || len(entries) > 0 {
		return
	}

	// ── Step 1: initial choice ────────────────────────────────────────────────

	var choice string
	err = huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("No endpoints installed yet").
				Description("How would you like to start your node?").
				Options(
					huh.NewOption("Start empty  —  add endpoints later", "empty"),
					huh.NewOption("Browse marketplace", "marketplace"),
				).
				Value(&choice),
		),
	).WithTheme(huh.ThemeCharm()).Run()

	if err != nil || choice != "marketplace" {
		return
	}

	// ── Step 2: fetch packages with a spinner ─────────────────────────────────

	manifestURL := cfg.GetMarketplaceURL()
	if manifestURL == "" {
		output.Warning("Marketplace URL not configured.")
		return
	}

	client := nodeops.NewMarketplaceClient(manifestURL)

	var (
		packages []nodeops.MarketplacePackage
		fetchErr error
		wg       sync.WaitGroup
		stop     = make(chan struct{})
	)

	wg.Add(1)
	go func() {
		defer wg.Done()
		frames := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
		i := 0
		for {
			select {
			case <-stop:
				return
			default:
				fmt.Printf("\r  %s  Fetching marketplace…", output.Dim.Sprint(frames[i%len(frames)]))
				i++
				time.Sleep(80 * time.Millisecond)
			}
		}
	}()

	packages, fetchErr = client.FetchPackages()
	close(stop)
	wg.Wait()
	fmt.Print("\r\033[K") // erase spinner line

	if fetchErr != nil {
		output.Warning("Could not reach marketplace (%v). Starting empty.", fetchErr)
		return
	}
	if len(packages) == 0 {
		output.Warning("No packages available. Starting empty.")
		return
	}

	// ── Step 3: multi-select ──────────────────────────────────────────────────

	// Sort: agents first, then models, then data_sources; alphabetically within each group.
	typeOrder := map[string]int{"agent": 0, "model": 1, "data_source": 2}
	sort.Slice(packages, func(i, j int) bool {
		ti := pkgDisplayType(packages[i])
		tj := pkgDisplayType(packages[j])
		if typeOrder[ti] != typeOrder[tj] {
			return typeOrder[ti] < typeOrder[tj]
		}
		return packages[i].Name < packages[j].Name
	})

	// Compute max name length for column alignment.
	maxNameLen := 0
	for _, pkg := range packages {
		if len(pkg.Name) > maxNameLen {
			maxNameLen = len(pkg.Name)
		}
	}

	opts := make([]huh.Option[string], len(packages))
	for i, pkg := range packages {
		dt := pkgDisplayType(pkg)
		badge := output.TypeBadge(dt)
		name := fmt.Sprintf("%-*s", maxNameLen, pkg.Name)
		ver := output.Dim.Sprintf("v%-6s", pkg.Version)
		desc := output.Dim.Sprint(output.Truncate(pkg.Description, 42))
		label := fmt.Sprintf("%s  %s  %s  %s", badge, name, ver, desc)
		opts[i] = huh.NewOption(label, pkg.Slug)
	}

	var selected []string
	err = huh.NewForm(
		huh.NewGroup(
			huh.NewMultiSelect[string]().
				Title("Marketplace packages").
				Description("Pick one or more packages to install with your node.").
				Options(opts...).
				Value(&selected).
				Height(12),
		),
	).WithTheme(huh.ThemeCharm()).Run()

	if err != nil || len(selected) == 0 {
		return
	}

	// ── Step 4: install ───────────────────────────────────────────────────────

	fmt.Println()
	for _, slug := range selected {
		idx := slices.IndexFunc(packages, func(p nodeops.MarketplacePackage) bool { return p.Slug == slug })
		if idx < 0 {
			continue
		}
		pkg := packages[idx]
		fmt.Printf("  Installing %s… ", output.Cyan.Sprint(pkg.Slug))

		if err := client.InstallPackage(cfg.EndpointsPath, pkg.Slug, pkg.DownloadURL); err != nil {
			output.Red.Printf("✗  %v\n", err)
			continue
		}
		output.Green.Println("✓")

		endpointDir := filepath.Join(cfg.EndpointsPath, pkg.Slug)
		spec, _ := nodeops.ParseSetupYaml(filepath.Join(endpointDir, "setup.yaml"))
		if spec != nil {
			fmt.Printf("\n  Configuring %s…\n\n", output.Cyan.Sprint(pkg.Slug))
			state := &nodeops.SetupState{Version: "1", Steps: map[string]nodeops.StepState{}}
			engine := handlers.NewDefaultEngine()
			sctx := &setupflow.SetupContext{
				EndpointDir: endpointDir,
				Slug:        pkg.Slug,
				HubURL:      cfg.HubURL,
				APIKey:      cfg.APIToken,
				IO:          NewCLISetupIO(),
				StepOutputs: make(map[string]*setupflow.StepResult),
				State:       state,
				Spec:        spec,
			}
			if err := engine.Execute(sctx); err != nil {
				output.Warning("Setup incomplete: %v", err)
				output.Info("Run 'syft node endpoint setup %s' to complete.", pkg.Slug)
			}
		}
	}
	fmt.Println()
}

// startNodeDaemon spawns "syft node run" as a detached background process
// with stdout/stderr redirected to the log file.
func startNodeDaemon() (int, error) {
	exe, err := os.Executable()
	if err != nil {
		return 0, fmt.Errorf("failed to find executable path: %w", err)
	}

	// Kill any orphaned node processes before starting a new one.
	// Orphans accumulate when a previous node was force-stopped and leave stale
	// NATS subscriptions that respond with DECRYPTION_FAILED to new requests.
	killOrphanedNodes()

	logFile, err := os.OpenFile(nodeconfig.LogFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return 0, fmt.Errorf("failed to open log file: %w", err)
	}

	cmd := exec.Command(exe, "node", "run")
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}

	if err := cmd.Start(); err != nil {
		logFile.Close()
		return 0, fmt.Errorf("failed to start daemon: %w", err)
	}

	pid := cmd.Process.Pid
	logFile.Close()
	cmd.Process.Release()

	// Brief wait to catch an immediate crash
	time.Sleep(500 * time.Millisecond)
	proc, err := os.FindProcess(pid)
	if err == nil {
		if err := proc.Signal(syscall.Signal(0)); err != nil {
			return 0, fmt.Errorf("daemon exited immediately — check logs at %s", nodeconfig.LogFile)
		}
	}

	return pid, nil
}

// stopExistingNode stops any currently running node daemon.
func stopExistingNode() {
	pid, err := nodeconfig.ReadPID()
	if err != nil {
		return
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		nodeconfig.RemovePID()
		return
	}
	if err := proc.Signal(syscall.Signal(0)); err != nil {
		nodeconfig.RemovePID()
		return
	}
	_ = proc.Signal(syscall.SIGTERM)
	for range 10 {
		time.Sleep(500 * time.Millisecond)
		if err := proc.Signal(syscall.Signal(0)); err != nil {
			break
		}
	}
	// Force-kill if still alive after graceful shutdown window.
	if proc.Signal(syscall.Signal(0)) == nil {
		_ = proc.Signal(syscall.SIGKILL)
	}
	nodeconfig.RemovePID()
}

// killOrphanedNodes terminates any "syft node run" processes not tracked by
// the PID file. These can accumulate when the node is force-stopped or
// crashes without closing its NATS connection, causing multiple stale
// subscribers on the same NATS subject and spurious DECRYPTION_FAILED errors.
func killOrphanedNodes() {
	exe, err := os.Executable()
	if err != nil {
		return
	}
	exeBase := filepath.Base(exe)

	entries, err := os.ReadDir("/proc")
	if err != nil {
		return // non-Linux: skip
	}

	trackedPID, _ := nodeconfig.ReadPID()
	selfPID := os.Getpid()

	// Phase 1: collect matching PIDs and send SIGTERM.
	var targets []int
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(e.Name())
		if err != nil || pid == selfPID || pid == trackedPID {
			continue
		}
		cmdlineBytes, err := os.ReadFile(fmt.Sprintf("/proc/%d/cmdline", pid))
		if err != nil {
			continue
		}
		cmdline := strings.ReplaceAll(string(cmdlineBytes), "\x00", " ")
		if strings.Contains(cmdline, exeBase) && strings.Contains(cmdline, "node run") {
			if proc, err := os.FindProcess(pid); err == nil {
				_ = proc.Signal(syscall.SIGTERM)
				targets = append(targets, pid)
			}
		}
	}

	if len(targets) == 0 {
		return
	}

	// Phase 2: poll until all targets exit or the deadline expires, then SIGKILL survivors.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		allDead := true
		for _, pid := range targets {
			if proc, err := os.FindProcess(pid); err == nil {
				if proc.Signal(syscall.Signal(0)) == nil {
					allDead = false
					break
				}
			}
		}
		if allDead {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	for _, pid := range targets {
		if proc, err := os.FindProcess(pid); err == nil {
			_ = proc.Signal(syscall.SIGKILL)
		}
	}
}

func promptRequired(reader *bufio.Reader, label string) string {
	for {
		fmt.Printf("%s: ", label)
		line, _ := reader.ReadString('\n')
		line = strings.TrimSpace(line)
		if line != "" {
			return line
		}
		fmt.Println("  This field is required.")
	}
}
