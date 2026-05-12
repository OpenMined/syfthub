package nodeops

import (
	"bufio"
	"errors"
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

// ReadRequirementsTxt reads a requirements.txt file and returns its raw
// dependency lines, skipping blank lines, comments, editable installs (-e),
// and recursive includes (-r). Returns nil, nil if the file does not exist.
func ReadRequirementsTxt(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return nil, err
	}
	defer file.Close()

	var deps []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "-e") || strings.HasPrefix(line, "-r") {
			continue
		}
		deps = append(deps, line)
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return deps, nil
}

// ReadPyprojectDepsWithExtras reads a pyproject.toml file and returns the raw
// dependency strings from [project.dependencies] (including extras matching
// any of the requested extras names in [project.optional-dependencies.X]).
// Inline `dependencies = [...]` and `extra_name = [...]` arrays are also
// supported. Returns raw entries (e.g. `numpy[cuda]>=1.0`) suitable to pass
// to pip install. Returns nil, nil if the file does not exist.
func ReadPyprojectDepsWithExtras(path string, extras []string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return nil, err
	}
	defer file.Close()

	var deps []string
	scanner := bufio.NewScanner(file)
	inDeps := false
	inOptionalDeps := false

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Section headers
		if line == "[project.dependencies]" {
			inDeps = true
			continue
		}
		if strings.HasPrefix(line, "[project.optional-dependencies.") {
			extra := strings.TrimSuffix(strings.TrimPrefix(line, "[project.optional-dependencies."), "]")
			inOptionalDeps = false
			for _, e := range extras {
				if e == extra {
					inOptionalDeps = true
					break
				}
			}
			continue
		}
		if strings.HasPrefix(line, "[") {
			inDeps = false
			inOptionalDeps = false
			continue
		}

		// Inline dependencies = [...] (handled via shared helper)
		if strings.HasPrefix(line, "dependencies = [") {
			if entries, ok := ParseInlineDeps(line); ok {
				for _, entry := range entries {
					deps = append(deps, strings.Trim(entry, `"'`))
				}
				continue
			}
			// Multi-line array start
			inDeps = true
			continue
		}

		// Inline extras format: extra_name = ["dep1", "dep2"]
		for _, extra := range extras {
			prefix := extra + " = ["
			if strings.HasPrefix(line, prefix) && strings.Contains(line, "]") {
				inner := line[len(prefix):strings.Index(line, "]")]
				for _, dep := range strings.Split(inner, ",") {
					dep = strings.Trim(dep, `"' `)
					if dep != "" {
						deps = append(deps, dep)
					}
				}
			}
		}

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") || line == "]" {
			if line == "]" {
				inDeps = false
				inOptionalDeps = false
			}
			continue
		}

		// Multi-line array entries
		if inDeps || inOptionalDeps {
			dep := strings.Trim(line, `"',`)
			if dep != "" {
				deps = append(deps, dep)
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return deps, nil
}
