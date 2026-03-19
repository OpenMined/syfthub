package nodeops

import (
	"os"
	"regexp"
	"strings"
)

// depRegex matches Python dependency lines in pyproject.toml.
var depRegex = regexp.MustCompile(`^["']?([a-zA-Z0-9_-]+)([><=!~]+)?([0-9.]+)?["']?,?$`)

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

		if line == "[project.dependencies]" || strings.HasPrefix(line, "dependencies = [") {
			inDeps = true
			continue
		}

		if inDeps && (strings.HasPrefix(line, "[") || line == "]") {
			if line == "]" {
				continue
			}
			inDeps = false
			continue
		}

		if inDeps && line != "" && !strings.HasPrefix(line, "#") {
			match := depRegex.FindStringSubmatch(line)
			if len(match) >= 2 {
				pkg := match[1]
				version := ""
				if len(match) >= 4 && match[3] != "" {
					version = match[3]
				}
				deps = append(deps, Dependency{Package: pkg, Version: version})
			}
		}
	}

	return deps, nil
}
