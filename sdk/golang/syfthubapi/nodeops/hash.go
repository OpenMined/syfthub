package nodeops

import (
	"crypto/sha256"
	"encoding/hex"
	"sort"
)

// HashString returns the full hex-encoded SHA-256 of s.
func HashString(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

// HashSortedLines returns the SHA-256 hex of the lines, sorted to make output
// independent of input order. Each line is followed by "\n" in the digest input.
// Used for cache keys over unordered collections (e.g. dependency lists).
func HashSortedLines(lines []string) string {
	sorted := make([]string, len(lines))
	copy(sorted, lines)
	sort.Strings(sorted)
	h := sha256.New()
	for _, l := range sorted {
		h.Write([]byte(l))
		h.Write([]byte("\n"))
	}
	return hex.EncodeToString(h.Sum(nil))
}

// HashShort returns the first 12 hex characters of HashString(s).
func HashShort(s string) string {
	return HashString(s)[:12]
}
