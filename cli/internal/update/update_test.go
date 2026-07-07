package update

import (
	"testing"
)

func TestParseSemVer(t *testing.T) {
	tests := []struct {
		input string
		want  SemVer
	}{
		{"0.1.0", SemVer{0, 1, 0, ""}},
		{"v0.1.0", SemVer{0, 1, 0, ""}},
		{"1.2.3", SemVer{1, 2, 3, ""}},
		{"0.2.0-beta.1", SemVer{0, 2, 0, "beta.1"}},
		{"v0.2.0-beta.1", SemVer{0, 2, 0, "beta.1"}},
		{"1.0.0-alpha.1", SemVer{1, 0, 0, "alpha.1"}},
		{"1.0.0-rc.1", SemVer{1, 0, 0, "rc.1"}},
		{"dev", SemVer{0, 0, 0, ""}},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := ParseSemVer(tt.input)
			if got != tt.want {
				t.Errorf("ParseSemVer(%q) = %+v, want %+v", tt.input, got, tt.want)
			}
		})
	}
}

func TestIsPreRelease(t *testing.T) {
	tests := []struct {
		input string
		want  bool
	}{
		{"0.1.0", false},
		{"v0.1.0", false},
		{"0.2.0-beta.1", true},
		{"0.2.0-alpha.1", true},
		{"0.2.0-rc.1", true},
		{"v1.0.0-beta.2", true},
		{"dev", false},
		{"0.2.0-hotfix.1", false}, // not a standard pre-release label
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := IsPreRelease(tt.input)
			if got != tt.want {
				t.Errorf("IsPreRelease(%q) = %v, want %v", tt.input, got, tt.want)
			}
		})
	}
}

func TestIsNewerVersion(t *testing.T) {
	tests := []struct {
		name    string
		latest  string
		current string
		want    bool
	}{
		// Basic version comparisons
		{"higher major", "2.0.0", "1.0.0", true},
		{"lower major", "1.0.0", "2.0.0", false},
		{"higher minor", "0.2.0", "0.1.0", true},
		{"lower minor", "0.1.0", "0.2.0", false},
		{"higher patch", "0.1.1", "0.1.0", true},
		{"lower patch", "0.1.0", "0.1.1", false},
		{"same version", "0.1.0", "0.1.0", false},

		// Pre-release vs stable (same base)
		{"stable newer than beta", "0.2.0", "0.2.0-beta.1", true},
		{"beta not newer than stable", "0.2.0-beta.1", "0.2.0", false},
		{"stable newer than alpha", "1.0.0", "1.0.0-alpha.1", true},
		{"stable newer than rc", "1.0.0", "1.0.0-rc.1", true},

		// Pre-release vs stable (different base)
		{"beta higher base wins", "0.3.0-beta.1", "0.2.0", true},
		{"beta lower base loses", "0.1.0-beta.1", "0.2.0", false},

		// Pre-release ordering (same base)
		{"beta.2 > beta.1", "0.2.0-beta.2", "0.2.0-beta.1", true},
		{"beta.1 < beta.2", "0.2.0-beta.1", "0.2.0-beta.2", false},
		{"rc > beta", "0.2.0-rc.1", "0.2.0-beta.1", true},
		{"beta > alpha", "0.2.0-beta.1", "0.2.0-alpha.1", true},
		{"alpha < beta", "0.2.0-alpha.1", "0.2.0-beta.1", false},
		{"same pre-release", "0.2.0-beta.1", "0.2.0-beta.1", false},

		// dev version (treated as 0.0.0 stable)
		{"any version newer than dev", "0.1.0", "dev", true},
		{"beta newer than dev", "0.1.0-beta.1", "dev", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := IsNewerVersion(tt.latest, tt.current)
			if got != tt.want {
				t.Errorf("IsNewerVersion(%q, %q) = %v, want %v",
					tt.latest, tt.current, got, tt.want)
			}
		})
	}
}

func TestParseVersion(t *testing.T) {
	// Backward compat: ParseVersion returns base version as []int
	tests := []struct {
		input string
		want  []int
	}{
		{"0.1.0", []int{0, 1, 0}},
		{"v1.2.3", []int{1, 2, 3}},
		{"0.2.0-beta.1", []int{0, 2, 0}},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := ParseVersion(tt.input)
			if len(got) != len(tt.want) {
				t.Fatalf("ParseVersion(%q) len = %d, want %d", tt.input, len(got), len(tt.want))
			}
			for i := range got {
				if got[i] != tt.want[i] {
					t.Errorf("ParseVersion(%q)[%d] = %d, want %d", tt.input, i, got[i], tt.want[i])
				}
			}
		})
	}
}
