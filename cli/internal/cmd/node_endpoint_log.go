package cmd

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var (
	nodeEndpointLogFollow bool
	nodeEndpointLogLimit  int
	nodeEndpointLogJSON   bool
)

var nodeEndpointLogCmd = &cobra.Command{
	Use:   "log <slug>",
	Short: "View request logs for an endpoint",
	Long: `Display request logs for a specific endpoint.

Logs show incoming requests, responses, timing, and policy decisions —
similar to the Logs tab in syfthub-desktop.

Use -f to follow new log entries in real time.`,
	Args: cobra.ExactArgs(1),
	RunE: runNodeEndpointLog,
}

func init() {
	nodeEndpointLogCmd.Flags().BoolVarP(&nodeEndpointLogFollow, "follow", "f", false, "Follow log output in real time")
	nodeEndpointLogCmd.Flags().IntVarP(&nodeEndpointLogLimit, "limit", "n", 50, "Number of recent log entries to show")
	nodeEndpointLogCmd.Flags().BoolVar(&nodeEndpointLogJSON, "json", false, "Output as raw JSON lines")
}

// logEntry is a lightweight struct for reading request log JSONL files.
type logEntry struct {
	ID            string    `json:"id"`
	Timestamp     time.Time `json:"timestamp"`
	EndpointSlug  string    `json:"endpoint_slug"`
	EndpointType  string    `json:"endpoint_type"`
	CorrelationID string    `json:"correlation_id"`
	User          *struct {
		Username string `json:"username"`
		Email    string `json:"email"`
	} `json:"user,omitempty"`
	Request *struct {
		Type    string `json:"type"`
		RawSize int    `json:"raw_size"`
		Query   string `json:"query,omitempty"`
	} `json:"request,omitempty"`
	Response *struct {
		Success bool   `json:"success"`
		Error   string `json:"error,omitempty"`
	} `json:"response,omitempty"`
	Policy *struct {
		Evaluated  bool   `json:"evaluated"`
		Allowed    bool   `json:"allowed"`
		PolicyName string `json:"policy_name,omitempty"`
		Reason     string `json:"reason,omitempty"`
	} `json:"policy,omitempty"`
	Timing *struct {
		DurationMs int64 `json:"duration_ms"`
	} `json:"timing,omitempty"`
}

func runNodeEndpointLog(cmd *cobra.Command, args []string) error {
	slug := args[0]
	logDir := filepath.Join(nodeconfig.LogsDir, slug)

	if _, err := os.Stat(logDir); os.IsNotExist(err) {
		if nodeEndpointLogJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": fmt.Sprintf("No logs found for endpoint '%s'", slug),
			})
		} else {
			output.Error("No logs found for endpoint '%s'", slug)
			fmt.Println("Logs are recorded when the node processes requests for this endpoint.")
		}
		return nil
	}

	if nodeEndpointLogFollow {
		return followEndpointLogs(logDir, slug)
	}

	return showRecentLogs(logDir, slug)
}

func showRecentLogs(logDir, slug string) error {
	// Read all JSONL files, sorted by date descending
	files, err := getLogFiles(logDir)
	if err != nil {
		return fmt.Errorf("failed to read log directory: %w", err)
	}

	if len(files) == 0 {
		if nodeEndpointLogJSON {
			output.JSON(map[string]interface{}{
				"status": "success",
				"logs":   []interface{}{},
				"total":  0,
			})
		} else {
			fmt.Printf("No log entries for endpoint '%s'.\n", slug)
		}
		return nil
	}

	// Collect entries from files (most recent first)
	var entries []logEntry
	for _, file := range files {
		fileEntries, err := readLogFile(filepath.Join(logDir, file))
		if err != nil {
			continue
		}
		entries = append(entries, fileEntries...)
		if len(entries) >= nodeEndpointLogLimit {
			break
		}
	}

	// Sort by timestamp descending
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Timestamp.After(entries[j].Timestamp)
	})

	// Trim to limit
	if len(entries) > nodeEndpointLogLimit {
		entries = entries[:nodeEndpointLogLimit]
	}

	if nodeEndpointLogJSON {
		output.JSON(map[string]interface{}{
			"status": "success",
			"logs":   entries,
			"total":  len(entries),
		})
		return nil
	}

	if len(entries) == 0 {
		fmt.Printf("No log entries for endpoint '%s'.\n", slug)
		return nil
	}

	// Display in reverse order (oldest first) for natural reading
	for i := len(entries) - 1; i >= 0; i-- {
		printLogEntry(&entries[i])
	}

	fmt.Printf("\nShowing %d most recent entries. Use -n to change the limit.\n", len(entries))
	return nil
}

func followEndpointLogs(logDir, slug string) error {
	fmt.Printf("Following logs for '%s' (Ctrl+C to stop)...\n\n", slug)

	// Start by showing the last few entries
	today := time.Now().Format("2006-01-02")
	todayFile := filepath.Join(logDir, today+".jsonl")

	var offset int64

	// Print existing entries from today's file
	if f, err := os.Open(todayFile); err == nil {
		scanner := bufio.NewScanner(f)
		buf := make([]byte, 1024*1024)
		scanner.Buffer(buf, 1024*1024)
		for scanner.Scan() {
			line := scanner.Bytes()
			if len(line) == 0 {
				continue
			}
			var entry logEntry
			if err := json.Unmarshal(line, &entry); err == nil {
				if nodeEndpointLogJSON {
					fmt.Println(string(line))
				} else {
					printLogEntry(&entry)
				}
			}
		}
		offset, _ = f.Seek(0, io.SeekCurrent)
		f.Close()
	}

	// Poll for new entries
	for {
		time.Sleep(500 * time.Millisecond)

		// Check if the date rolled over
		currentDate := time.Now().Format("2006-01-02")
		currentFile := filepath.Join(logDir, currentDate+".jsonl")
		if currentDate != today {
			today = currentDate
			offset = 0
		}

		f, err := os.Open(currentFile)
		if err != nil {
			continue
		}

		if offset > 0 {
			f.Seek(offset, io.SeekStart)
		}

		scanner := bufio.NewScanner(f)
		buf := make([]byte, 1024*1024)
		scanner.Buffer(buf, 1024*1024)
		for scanner.Scan() {
			line := scanner.Bytes()
			if len(line) == 0 {
				continue
			}
			var entry logEntry
			if err := json.Unmarshal(line, &entry); err == nil {
				if nodeEndpointLogJSON {
					fmt.Println(string(line))
				} else {
					printLogEntry(&entry)
				}
			}
		}

		offset, _ = f.Seek(0, io.SeekCurrent)
		f.Close()
	}
}

func printLogEntry(e *logEntry) {
	ts := e.Timestamp.Local().Format("2006-01-02 15:04:05")

	status := "OK"
	if e.Response != nil && !e.Response.Success {
		status = "ERR"
	}
	if e.Policy != nil && e.Policy.Evaluated && !e.Policy.Allowed {
		status = "DENIED"
	}

	user := "-"
	if e.User != nil && e.User.Username != "" {
		user = e.User.Username
	}

	duration := "-"
	if e.Timing != nil {
		duration = fmt.Sprintf("%dms", e.Timing.DurationMs)
	}

	// Status color
	statusStr := status
	switch status {
	case "OK":
		statusStr = "\033[32m" + status + "\033[0m" // green
	case "ERR":
		statusStr = "\033[31m" + status + "\033[0m" // red
	case "DENIED":
		statusStr = "\033[33m" + status + "\033[0m" // yellow
	}

	fmt.Printf("[%s] %-6s  user=%-15s  duration=%-8s", ts, statusStr, user, duration)

	// Extra details
	var details []string
	if e.Response != nil && e.Response.Error != "" {
		errMsg := e.Response.Error
		if len(errMsg) > 60 {
			errMsg = errMsg[:57] + "..."
		}
		details = append(details, "error="+errMsg)
	}
	if e.Policy != nil && e.Policy.Evaluated && !e.Policy.Allowed {
		reason := e.Policy.Reason
		if reason == "" {
			reason = e.Policy.PolicyName
		}
		details = append(details, "policy="+reason)
	}
	if e.Request != nil && e.Request.Query != "" {
		q := e.Request.Query
		if len(q) > 40 {
			q = q[:37] + "..."
		}
		details = append(details, "query="+q)
	}

	if len(details) > 0 {
		fmt.Printf("  %s", strings.Join(details, "  "))
	}
	fmt.Println()
}

// getLogFiles returns JSONL files sorted by date descending.
func getLogFiles(logDir string) ([]string, error) {
	entries, err := os.ReadDir(logDir)
	if err != nil {
		return nil, err
	}

	var files []string
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".jsonl") {
			files = append(files, entry.Name())
		}
	}

	sort.Slice(files, func(i, j int) bool {
		return files[i] > files[j] // descending by date
	})

	return files, nil
}

// readLogFile reads all entries from a JSONL file.
func readLogFile(path string) ([]logEntry, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var entries []logEntry
	scanner := bufio.NewScanner(f)
	buf := make([]byte, 1024*1024)
	scanner.Buffer(buf, 1024*1024)

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var entry logEntry
		if err := json.Unmarshal(line, &entry); err == nil {
			entries = append(entries, entry)
		}
	}

	return entries, scanner.Err()
}
