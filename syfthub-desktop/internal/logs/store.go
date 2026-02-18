// Package logs provides request logging functionality for syfthub-desktop.
package logs

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// FileLogStore implements LogStore using JSON Lines files.
// Logs are stored per-endpoint in daily files for easy ETL processing.
type FileLogStore struct {
	basePath string         // Base path for all logs (e.g., ~/.config/syfthub-desktop/logs)
	writeCh  chan writeJob  // Channel for async writes
	done     chan struct{}  // Signal to stop writer goroutine
	wg       sync.WaitGroup // Wait for writer to finish
	mu       sync.RWMutex   // Protects file operations
}

// writeJob represents a pending write operation.
type writeJob struct {
	slug  string
	entry *syfthubapi.RequestLog
}

// NewFileLogStore creates a new file-based log store.
func NewFileLogStore(basePath string) (*FileLogStore, error) {
	// Ensure base path exists
	if err := os.MkdirAll(basePath, 0755); err != nil {
		return nil, fmt.Errorf("failed to create log directory: %w", err)
	}

	store := &FileLogStore{
		basePath: basePath,
		writeCh:  make(chan writeJob, 1000), // Buffer up to 1000 writes
		done:     make(chan struct{}),
	}

	// Start async writer goroutine
	store.wg.Add(1)
	go store.writerLoop()

	return store, nil
}

// Write appends a log entry asynchronously.
func (s *FileLogStore) Write(ctx context.Context, entry *syfthubapi.RequestLog) error {
	select {
	case s.writeCh <- writeJob{slug: entry.EndpointSlug, entry: entry}:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	case <-s.done:
		return fmt.Errorf("log store is closed")
	}
}

// Query retrieves logs for an endpoint with optional filters.
func (s *FileLogStore) Query(ctx context.Context, slug string, opts *syfthubapi.LogQueryOptions) (*syfthubapi.LogQueryResult, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if opts == nil {
		opts = &syfthubapi.LogQueryOptions{Limit: 100}
	}
	if opts.Limit <= 0 {
		opts.Limit = 100
	}

	logDir := s.endpointLogDir(slug)

	// Check if directory exists
	if _, err := os.Stat(logDir); os.IsNotExist(err) {
		return &syfthubapi.LogQueryResult{
			Logs:    []*syfthubapi.RequestLog{},
			Total:   0,
			HasMore: false,
		}, nil
	}

	// Get all log files for this endpoint
	files, err := s.getLogFiles(logDir)
	if err != nil {
		return nil, fmt.Errorf("failed to list log files: %w", err)
	}

	// Filter files by date range if specified
	if opts.StartTime != nil || opts.EndTime != nil {
		files = s.filterFilesByDateRange(files, opts.StartTime, opts.EndTime)
	}

	// Read and filter logs
	var allLogs []*syfthubapi.RequestLog
	for _, file := range files {
		logs, err := s.readLogFile(filepath.Join(logDir, file))
		if err != nil {
			continue // Skip files with errors
		}

		// Apply filters
		for _, log := range logs {
			if s.matchesFilters(log, opts) {
				allLogs = append(allLogs, log)
			}
		}
	}

	// Sort by timestamp descending (most recent first)
	sort.Slice(allLogs, func(i, j int) bool {
		return allLogs[i].Timestamp.After(allLogs[j].Timestamp)
	})

	// Apply pagination
	total := len(allLogs)
	start := opts.Offset
	if start > total {
		start = total
	}
	end := start + opts.Limit
	if end > total {
		end = total
	}

	return &syfthubapi.LogQueryResult{
		Logs:    allLogs[start:end],
		Total:   total,
		HasMore: end < total,
	}, nil
}

// GetStats returns aggregate statistics for an endpoint.
func (s *FileLogStore) GetStats(ctx context.Context, slug string) (*syfthubapi.LogStats, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	logDir := s.endpointLogDir(slug)

	// Check if directory exists
	if _, err := os.Stat(logDir); os.IsNotExist(err) {
		return &syfthubapi.LogStats{}, nil
	}

	files, err := s.getLogFiles(logDir)
	if err != nil {
		return nil, fmt.Errorf("failed to list log files: %w", err)
	}

	stats := &syfthubapi.LogStats{}
	var totalDuration int64
	var lastTime time.Time

	for _, file := range files {
		logs, err := s.readLogFile(filepath.Join(logDir, file))
		if err != nil {
			continue
		}

		for _, log := range logs {
			stats.TotalRequests++

			if log.Response != nil {
				if log.Response.Success {
					stats.SuccessCount++
				} else {
					stats.ErrorCount++
				}
			}

			if log.Policy != nil && log.Policy.Evaluated && !log.Policy.Allowed {
				stats.PolicyDenyCount++
			}

			if log.Timing != nil {
				totalDuration += log.Timing.DurationMs
			}

			if log.Timestamp.After(lastTime) {
				lastTime = log.Timestamp
			}
		}
	}

	if stats.TotalRequests > 0 {
		stats.AvgDurationMs = float64(totalDuration) / float64(stats.TotalRequests)
	}

	if !lastTime.IsZero() {
		stats.LastRequestTime = &lastTime
	}

	return stats, nil
}

// Close stops the writer goroutine and flushes pending writes.
func (s *FileLogStore) Close() error {
	close(s.done)
	s.wg.Wait()
	return nil
}

// writerLoop is the async writer goroutine.
func (s *FileLogStore) writerLoop() {
	defer s.wg.Done()

	for {
		select {
		case job := <-s.writeCh:
			s.writeEntry(job.slug, job.entry)
		case <-s.done:
			// Drain remaining writes
			for {
				select {
				case job := <-s.writeCh:
					s.writeEntry(job.slug, job.entry)
				default:
					return
				}
			}
		}
	}
}

// writeEntry writes a single log entry to the appropriate file.
func (s *FileLogStore) writeEntry(slug string, entry *syfthubapi.RequestLog) {
	s.mu.Lock()
	defer s.mu.Unlock()

	logDir := s.endpointLogDir(slug)
	if err := os.MkdirAll(logDir, 0755); err != nil {
		return // Silently fail - don't block on log errors
	}

	// Use date-based file naming
	date := entry.Timestamp.Format("2006-01-02")
	filename := filepath.Join(logDir, date+".jsonl")

	// Open file in append mode
	f, err := os.OpenFile(filename, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()

	// Write JSON line
	data, err := json.Marshal(entry)
	if err != nil {
		return
	}

	f.Write(data)
	f.Write([]byte("\n"))
}

// endpointLogDir returns the log directory for an endpoint.
func (s *FileLogStore) endpointLogDir(slug string) string {
	return filepath.Join(s.basePath, slug)
}

// getLogFiles returns all log files for an endpoint, sorted by date descending.
func (s *FileLogStore) getLogFiles(logDir string) ([]string, error) {
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

	// Sort by date descending (most recent first)
	sort.Slice(files, func(i, j int) bool {
		return files[i] > files[j]
	})

	return files, nil
}

// filterFilesByDateRange filters log files by date range.
func (s *FileLogStore) filterFilesByDateRange(files []string, startTime, endTime *time.Time) []string {
	var filtered []string
	for _, file := range files {
		// Extract date from filename (YYYY-MM-DD.jsonl)
		datePart := strings.TrimSuffix(file, ".jsonl")
		fileDate, err := time.Parse("2006-01-02", datePart)
		if err != nil {
			continue
		}

		// Include file if it overlaps with the date range
		if startTime != nil && fileDate.Before(startTime.Truncate(24*time.Hour)) {
			continue
		}
		if endTime != nil && fileDate.After(endTime.Truncate(24*time.Hour)) {
			continue
		}

		filtered = append(filtered, file)
	}
	return filtered
}

// readLogFile reads all log entries from a file.
func (s *FileLogStore) readLogFile(path string) ([]*syfthubapi.RequestLog, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var logs []*syfthubapi.RequestLog
	scanner := bufio.NewScanner(f)

	// Increase buffer size for large log lines
	const maxScannerBuffer = 1024 * 1024 // 1MB
	buf := make([]byte, maxScannerBuffer)
	scanner.Buffer(buf, maxScannerBuffer)

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var log syfthubapi.RequestLog
		if err := json.Unmarshal(line, &log); err != nil {
			continue // Skip malformed lines
		}
		logs = append(logs, &log)
	}

	return logs, scanner.Err()
}

// matchesFilters checks if a log entry matches the query filters.
func (s *FileLogStore) matchesFilters(log *syfthubapi.RequestLog, opts *syfthubapi.LogQueryOptions) bool {
	// Time range filter
	if opts.StartTime != nil && log.Timestamp.Before(*opts.StartTime) {
		return false
	}
	if opts.EndTime != nil && log.Timestamp.After(*opts.EndTime) {
		return false
	}

	// Status filter
	if opts.Status != "" {
		if opts.Status == "success" && (log.Response == nil || !log.Response.Success) {
			return false
		}
		if opts.Status == "error" && (log.Response == nil || log.Response.Success) {
			return false
		}
	}

	// User ID filter
	if opts.UserID != "" {
		if log.User == nil || log.User.ID != opts.UserID {
			return false
		}
	}

	// Policy only filter
	if opts.PolicyOnly {
		if log.Policy == nil || !log.Policy.Evaluated {
			return false
		}
	}

	return true
}

// GetLogByID retrieves a specific log entry by ID.
func (s *FileLogStore) GetLogByID(ctx context.Context, slug, logID string) (*syfthubapi.RequestLog, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	logDir := s.endpointLogDir(slug)

	files, err := s.getLogFiles(logDir)
	if err != nil {
		return nil, fmt.Errorf("failed to list log files: %w", err)
	}

	for _, file := range files {
		logs, err := s.readLogFile(filepath.Join(logDir, file))
		if err != nil {
			continue
		}

		for _, log := range logs {
			if log.ID == logID {
				return log, nil
			}
		}
	}

	return nil, fmt.Errorf("log entry not found: %s", logID)
}

// DeleteLogs deletes all logs for an endpoint.
func (s *FileLogStore) DeleteLogs(ctx context.Context, slug string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	logDir := s.endpointLogDir(slug)
	return os.RemoveAll(logDir)
}

// DefaultLogStorePath returns the default path for log storage.
func DefaultLogStorePath() (string, error) {
	configDir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(configDir, "syfthub-desktop", "logs"), nil
}
