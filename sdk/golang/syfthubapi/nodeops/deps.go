package nodeops

import (
	"os"
	"regexp"
	"strings"
)

// depNameRegex extracts the package name from a dependency string.
// Handles dotted names (zope.interface) and ignores extras ([cuda]).
var depNameRegex = regexp.MustCompile(`^["']?([a-zA-Z0-9._-]+)`)

// depVersionRegex extracts the first version number from a dependency string.
var depVersionRegex = regexp.MustCompile(`[><=!~]+\s*([0-9][0-9.]*)`)

// ParseInlineDeps splits a `dependencies = [...]` line that is closed on the
// same line into its raw entries (still quoted, e.g. `"numpy>=1.0"`).
// Returns nil, false if the line is not inline format.
func ParseInlineDeps(line string) ([]string, bool) {
	line = strings.TrimSpace(line)
	if !strings.HasPrefix(line, "dependencies = [") {
		return nil, false
	}
	rest := line[len("dependencies = ["):]
	idx := strings.LastIndex(rest, "]")
	if idx < 0 {
		return nil, false
	}
	inner := rest[:idx]
	var entries []string
	for _, entry := range strings.Split(inner, ",") {
		entry = strings.TrimSpace(entry)
		if entry != "" {
			entries = append(entries, entry)
		}
	}
	return entries, true
}

// MatchesDep reports whether a raw dependency string (e.g. "numpy>=1.0")
// refers to the given package name, handling version specifiers and extras.
func MatchesDep(entry, pkg string) bool {
	bare := strings.Trim(entry, `"'`)
	if bare == pkg {
		return true
	}
	for _, op := range []string{">=", "==", "<=", "~=", "!=", "===", ">", "<", "["} {
		if strings.HasPrefix(bare, pkg+op) {
			return true
		}
	}
	return false
}

// parseDep parses a single dependency string into a Dependency.
// Handles extras (numpy[cuda]>=1.0), dotted names (zope.interface),
// and compound specifiers (numpy>=1.0,<2.0).
func parseDep(entry string) (Dependency, bool) {
	entry = strings.Trim(entry, `"'`)
	nameMatch := depNameRegex.FindStringSubmatch(entry)
	if len(nameMatch) < 2 {
		return Dependency{}, false
	}
	version := ""
	if vMatch := depVersionRegex.FindStringSubmatch(entry); len(vMatch) >= 2 {
		version = vMatch[1]
	}
	return Dependency{Package: nameMatch[1], Version: version}, true
}

// ReadDependencies reads Python dependencies from a pyproject.toml file.
// Returns an empty slice (not nil) if the file doesn't exist.
func ReadDependencies(path string) ([]Dependency, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return []Dependency{}, nil
		}
		return nil, err
	}

	var deps []Dependency
	lines := strings.Split(string(content), "\n")
	inDeps := false

	for _, line := range lines {
		line = strings.TrimSpace(line)

		if line == "[project.dependencies]" {
			inDeps = true
			continue
		}

		if strings.HasPrefix(line, "dependencies = [") {
			if entries, ok := ParseInlineDeps(line); ok {
				for _, entry := range entries {
					if dep, ok := parseDep(entry); ok {
						deps = append(deps, dep)
					}
				}
				continue
			}
			// Opening bracket without close — multi-line array
			inDeps = true
			continue
		}

		if inDeps && (strings.HasPrefix(line, "[") || line == "]") {
			inDeps = false
			continue
		}

		if inDeps && line != "" && !strings.HasPrefix(line, "#") {
			if dep, ok := parseDep(line); ok {
				deps = append(deps, dep)
			}
		}
	}

	return deps, nil
}
