package nodeops

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"maps"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

// ParseReadmeFrontmatterBytes parses YAML frontmatter from README content already in memory.
// Returns (frontmatter, body, error) where body is the markdown content after frontmatter.
func ParseReadmeFrontmatterBytes(data []byte) (*ReadmeFrontmatter, string, error) {
	return parseFrontmatterFromReader(bytes.NewReader(data))
}

// ParseReadmeFrontmatter parses YAML frontmatter from a README.md file.
// Returns (frontmatter, body, error) where body is the markdown content after frontmatter.
func ParseReadmeFrontmatter(path string) (*ReadmeFrontmatter, string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, "", err
	}
	defer file.Close()
	return parseFrontmatterFromReader(file)
}

// SplitFrontmatter reads YAML frontmatter delimited by "---" from r.
// Returns the raw YAML bytes (between the delimiters) and the remaining body text.
// This is the single implementation of frontmatter splitting, shared by all parsers.
func SplitFrontmatter(r io.Reader) (yamlBytes []byte, body string, err error) {
	scanner := bufio.NewScanner(r)

	if !scanner.Scan() {
		return nil, "", fmt.Errorf("empty file")
	}

	firstLine := strings.TrimSpace(scanner.Text())
	if firstLine != "---" {
		return nil, "", fmt.Errorf("missing YAML frontmatter (expected '---')")
	}

	var yamlLines []string
	foundClose := false

	for scanner.Scan() {
		line := scanner.Text()
		if strings.TrimSpace(line) == "---" {
			foundClose = true
			break
		}
		yamlLines = append(yamlLines, line)
	}

	if err := scanner.Err(); err != nil {
		return nil, "", fmt.Errorf("error reading file: %w", err)
	}

	if !foundClose {
		return nil, "", fmt.Errorf("unclosed YAML frontmatter (missing closing '---')")
	}

	var bodyLines []string
	for scanner.Scan() {
		bodyLines = append(bodyLines, scanner.Text())
	}

	if err := scanner.Err(); err != nil {
		return nil, "", fmt.Errorf("error reading file body: %w", err)
	}

	return []byte(strings.Join(yamlLines, "\n")), strings.TrimSpace(strings.Join(bodyLines, "\n")), nil
}

func parseFrontmatterFromReader(r io.Reader) (*ReadmeFrontmatter, string, error) {
	yamlBytes, body, err := SplitFrontmatter(r)
	if err != nil {
		return nil, "", err
	}

	var frontmatter ReadmeFrontmatter
	if err := yaml.Unmarshal(yamlBytes, &frontmatter); err != nil {
		return nil, "", fmt.Errorf("invalid YAML frontmatter: %w", err)
	}

	return &frontmatter, body, nil
}

// UpdateReadmeFrontmatter updates specific fields in the README.md frontmatter
// while preserving the markdown body.
func UpdateReadmeFrontmatter(path string, updates map[string]any) error {
	content, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	lines := strings.Split(string(content), "\n")

	if len(lines) == 0 || strings.TrimSpace(lines[0]) != "---" {
		return fmt.Errorf("file does not have YAML frontmatter")
	}

	frontmatterEnd := -1
	for i := 1; i < len(lines); i++ {
		if strings.TrimSpace(lines[i]) == "---" {
			frontmatterEnd = i
			break
		}
	}

	if frontmatterEnd == -1 {
		return fmt.Errorf("unclosed YAML frontmatter")
	}

	yamlContent := strings.Join(lines[1:frontmatterEnd], "\n")
	var frontmatter map[string]any
	if err := yaml.Unmarshal([]byte(yamlContent), &frontmatter); err != nil {
		return fmt.Errorf("failed to parse frontmatter: %w", err)
	}

	maps.Copy(frontmatter, updates)

	newYaml, err := yaml.Marshal(frontmatter)
	if err != nil {
		return fmt.Errorf("failed to serialize frontmatter: %w", err)
	}

	var result strings.Builder
	result.WriteString("---\n")
	result.Write(newYaml)
	result.WriteString("---\n")

	if frontmatterEnd+1 < len(lines) {
		result.WriteString(strings.Join(lines[frontmatterEnd+1:], "\n"))
	}

	return os.WriteFile(path, []byte(result.String()), 0644)
}

// WriteReadmeWithFrontmatter writes a new README.md file with YAML frontmatter and body.
func WriteReadmeWithFrontmatter(path string, fm *ReadmeFrontmatter, body string) error {
	yamlBytes, err := yaml.Marshal(fm)
	if err != nil {
		return fmt.Errorf("failed to marshal frontmatter: %w", err)
	}

	var result strings.Builder
	result.WriteString("---\n")
	result.Write(yamlBytes)
	result.WriteString("---\n")
	if body != "" {
		result.WriteString("\n")
		result.WriteString(body)
		result.WriteString("\n")
	}

	return os.WriteFile(path, []byte(result.String()), 0644)
}
