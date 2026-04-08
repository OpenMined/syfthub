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

// scannerBufPool reuses 1MB scanner buffers to avoid allocating one per file read.
var scannerBufPool = sync.Pool{
	New: func() any {
		buf := make([]byte, 1024*1024)
		return &buf
	},
}

// cachedEndpointStats holds incrementally-maintained stats for a single endpoint slug.
type cachedEndpointStats struct {
	stats         syfthubapi.LogStats
	totalDuration int64
}

// FileLogStore implements LogStore using JSON Lines files.
// Logs are stored per-endpoint in daily files for easy ETL processing.
type FileLogStore struct {
	basePath string         // Base path for all logs (e.g., ~/.config/syfthub/logs)
	writeCh  chan writeJob  // Channel for async writes
	done     chan struct{}  // Signal to stop writer goroutine
	wg       sync.WaitGroup // Wait for writer to finish
	mu       sync.RWMutex   // Protects file operations

	// File handle cache: reuse open file handles instead of open/close per entry.
	fileHandles map[string]*os.File

	// Incremental stats cache: updated on each write, avoids full scans in GetStats().
	statsCache map[string]*cachedEndpointStats
	statsMu    sync.RWMutex // Protects statsCache
	statsReady bool         // True once initial scan is complete
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
		basePath:    basePath,
		writeCh:     make(chan writeJob, 1000), // Buffer up to 1000 writes
		done:        make(chan struct{}),
		fileHandles: make(map[string]*os.File),
		statsCache:  make(map[string]*cachedEndpointStats),
	}

	// Initialize stats cache from existing log files
	store.initStatsCache()

	// Start async writer goroutine
	store.wg.Add(1)
	go store.writerLoop()

	return store, nil
}

// initStatsCache performs a one-time full scan of all existing log files
// to populate the stats cache. Subsequent updates are incremental via writerLoop.
func (s *FileLogStore) initStatsCache() {
	entries, err := os.ReadDir(s.basePath)
	if err != nil {
		// No existing logs, that's fine
		s.statsReady = true
		return
	}

	for _, dirEntry := range entries {
		if !dirEntry.IsDir() {
			continue
		}
		slug := dirEntry.Name()
		logDir := s.endpointLogDir(slug)

		files, err := s.getLogFiles(logDir)
		if err != nil {
			continue
		}

		cached := &cachedEndpointStats{}
		var lastTime time.Time

		for _, file := range files {
			logs, err := s.readLogFile(filepath.Join(logDir, file))
			if err != nil {
				continue
			}

			for _, log := range logs {
				cached.stats.TotalRequests++

				if log.Response != nil {
					if log.Response.Success {
						cached.stats.SuccessCount++
					} else {
						cached.stats.ErrorCount++
					}
				}

				if log.Policy != nil && log.Policy.Evaluated && !log.Policy.Allowed {
					cached.stats.PolicyDenyCount++
				}

				if log.Timing != nil {
					cached.totalDuration += log.Timing.DurationMs
				}

				if log.Timestamp.After(lastTime) {
					lastTime = log.Timestamp
				}
			}
		}

		if cached.stats.TotalRequests > 0 {
			cached.stats.AvgDurationMs = float64(cached.totalDuration) / float64(cached.stats.TotalRequests)
		}

		if !lastTime.IsZero() {
			t := lastTime
			cached.stats.LastRequestTime = &t
		}

		s.statsCache[slug] = cached
	}

	s.statsReady = true
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

	// Get all log files for this endpoint (already sorted descending by date)
	files, err := s.getLogFiles(logDir)
	if err != nil {
		return nil, fmt.Errorf("failed to list log files: %w", err)
	}

	// Skip files outside the query's date range
	if opts.StartTime != nil || opts.EndTime != nil {
		files = s.filterFilesByDateRange(files, opts.StartTime, opts.EndTime)
	}

	// Read files in reverse chronological order (most recent first).
	// Collect matching entries, keeping only up to offset+limit in the result slice,
	// but continue counting total matches for accurate Total.
	needed := opts.Offset + opts.Limit
	var collected []*syfthubapi.RequestLog
	totalMatches := 0

	for _, file := range files {
		entries, err := s.readLogFileFiltered(filepath.Join(logDir, file), opts)
		if err != nil {
			continue
		}

		for _, entry := range entries {
			totalMatches++
			if len(collected) < needed {
				collected = append(collected, entry)
			}
		}
	}

	// Sort collected entries by timestamp descending (most recent first).
	// We only sort the smaller collected slice, not all entries.
	sort.Slice(collected, func(i, j int) bool {
		return collected[i].Timestamp.After(collected[j].Timestamp)
	})

	// Apply pagination on the collected entries
	start := opts.Offset
	if start > len(collected) {
		start = len(collected)
	}
	end := start + opts.Limit
	if end > len(collected) {
		end = len(collected)
	}

	return &syfthubapi.LogQueryResult{
		Logs:    collected[start:end],
		Total:   totalMatches,
		HasMore: end < totalMatches,
	}, nil
}

// readLogFileFiltered reads log entries from a file, applying filters inline.
// Only matching entries are returned, avoiding full deserialization into a temp slice.
func (s *FileLogStore) readLogFileFiltered(path string, opts *syfthubapi.LogQueryOptions) ([]*syfthubapi.RequestLog, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var logs []*syfthubapi.RequestLog
	scanner := bufio.NewScanner(f)

	// Get a buffer from the pool
	bufPtr := scannerBufPool.Get().(*[]byte)
	scanner.Buffer(*bufPtr, len(*bufPtr))

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var log syfthubapi.RequestLog
		if err := json.Unmarshal(line, &log); err != nil {
			continue // Skip malformed lines
		}

		if s.matchesFilters(&log, opts) {
			logs = append(logs, &log)
		}
	}

	// Return the buffer to the pool
	scannerBufPool.Put(bufPtr)

	if err := scanner.Err(); err != nil {
		return logs, err
	}

	return logs, nil
}

// GetStats returns aggregate statistics for an endpoint.
func (s *FileLogStore) GetStats(ctx context.Context, slug string) (*syfthubapi.LogStats, error) {
	s.statsMu.RLock()
	defer s.statsMu.RUnlock()

	// If we have cached stats, return a copy directly
	if s.statsReady {
		cached, ok := s.statsCache[slug]
		if !ok {
			return &syfthubapi.LogStats{}, nil
		}

		// Return a copy so the caller can't mutate our cache
		result := cached.stats
		if cached.stats.LastRequestTime != nil {
			t := *cached.stats.LastRequestTime
			result.LastRequestTime = &t
		}
		return &result, nil
	}

	// Fallback: full scan (should only happen if called before init completes)
	return s.getStatsFull(ctx, slug)
}

// getStatsFull performs a full scan for stats (fallback path).
func (s *FileLogStore) getStatsFull(_ context.Context, slug string) (*syfthubapi.LogStats, error) {
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

	// Close all cached file handles
	for path, f := range s.fileHandles {
		f.Close()
		delete(s.fileHandles, path)
	}

	return nil
}

// writerLoop is the async writer goroutine.
func (s *FileLogStore) writerLoop() {
	defer s.wg.Done()

	for {
		select {
		case job := <-s.writeCh:
			s.writeEntry(job.slug, job.entry)
			s.updateStatsCache(job.slug, job.entry)
		case <-s.done:
			// Drain remaining writes
			for {
				select {
				case job := <-s.writeCh:
					s.writeEntry(job.slug, job.entry)
					s.updateStatsCache(job.slug, job.entry)
				default:
					return
				}
			}
		}
	}
}

// updateStatsCache incrementally updates the cached stats for a slug after a write.
func (s *FileLogStore) updateStatsCache(slug string, entry *syfthubapi.RequestLog) {
	s.statsMu.Lock()
	defer s.statsMu.Unlock()

	cached, ok := s.statsCache[slug]
	if !ok {
		cached = &cachedEndpointStats{}
		s.statsCache[slug] = cached
	}

	cached.stats.TotalRequests++

	if entry.Response != nil {
		if entry.Response.Success {
			cached.stats.SuccessCount++
		} else {
			cached.stats.ErrorCount++
		}
	}

	if entry.Policy != nil && entry.Policy.Evaluated && !entry.Policy.Allowed {
		cached.stats.PolicyDenyCount++
	}

	if entry.Timing != nil {
		cached.totalDuration += entry.Timing.DurationMs
	}

	// Recompute average
	if cached.stats.TotalRequests > 0 {
		cached.stats.AvgDurationMs = float64(cached.totalDuration) / float64(cached.stats.TotalRequests)
	}

	if cached.stats.LastRequestTime == nil || entry.Timestamp.After(*cached.stats.LastRequestTime) {
		t := entry.Timestamp
		cached.stats.LastRequestTime = &t
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

	// Reuse cached file handle if available and for the same file
	f, ok := s.fileHandles[slug]
	if ok {
		// Check if the cached handle is for the correct file
		if f.Name() != filename {
			// Date rolled over: close the old handle, open a new one
			f.Close()
			delete(s.fileHandles, slug)
			f = nil
			ok = false
		}
	}

	if !ok {
		var err error
		f, err = os.OpenFile(filename, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err != nil {
			return
		}
		s.fileHandles[slug] = f
	}

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

	// Get a reusable buffer from the pool instead of allocating 1MB per call
	bufPtr := scannerBufPool.Get().(*[]byte)
	scanner.Buffer(*bufPtr, len(*bufPtr))

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

	// Return the buffer to the pool
	scannerBufPool.Put(bufPtr)

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
// Files are iterated in reverse chronological order (most recent first),
// and scanning stops immediately on the first match.
func (s *FileLogStore) GetLogByID(ctx context.Context, slug, logID string) (*syfthubapi.RequestLog, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	logDir := s.endpointLogDir(slug)

	files, err := s.getLogFiles(logDir)
	if err != nil {
		return nil, fmt.Errorf("failed to list log files: %w", err)
	}

	// Iterate files in reverse chronological order (already sorted descending).
	// Return immediately on first match to avoid scanning remaining files.
	for _, file := range files {
		entry, found, err := s.scanFileForID(filepath.Join(logDir, file), logID)
		if err != nil {
			continue
		}
		if found {
			return entry, nil
		}
	}

	return nil, fmt.Errorf("log entry not found: %s", logID)
}

// scanFileForID scans a single log file looking for an entry with the given ID.
// Returns the entry and true if found, nil and false otherwise.
func (s *FileLogStore) scanFileForID(path, logID string) (*syfthubapi.RequestLog, bool, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, false, err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)

	// Get a reusable buffer from the pool
	bufPtr := scannerBufPool.Get().(*[]byte)
	scanner.Buffer(*bufPtr, len(*bufPtr))

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var log syfthubapi.RequestLog
		if err := json.Unmarshal(line, &log); err != nil {
			continue
		}

		if log.ID == logID {
			scannerBufPool.Put(bufPtr)
			return &log, true, nil
		}
	}

	scannerBufPool.Put(bufPtr)
	return nil, false, scanner.Err()
}

// DeleteLogs deletes all logs for an endpoint.
func (s *FileLogStore) DeleteLogs(ctx context.Context, slug string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Close any cached file handle for this slug
	if f, ok := s.fileHandles[slug]; ok {
		f.Close()
		delete(s.fileHandles, slug)
	}

	// Clear the stats cache for this slug
	s.statsMu.Lock()
	delete(s.statsCache, slug)
	s.statsMu.Unlock()

	logDir := s.endpointLogDir(slug)
	return os.RemoveAll(logDir)
}

// DefaultLogStorePath returns the default path for log storage.
func DefaultLogStorePath() (string, error) {
	configDir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(configDir, "syfthub", "logs"), nil
}
