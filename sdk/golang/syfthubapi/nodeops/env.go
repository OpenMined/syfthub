package nodeops

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

// ReadEnvFile reads a .env file and returns key-value pairs.
// Returns an empty slice (not nil) if the file doesn't exist.
func ReadEnvFile(path string) ([]EnvVar, error) {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return []EnvVar{}, nil
		}
		return nil, err
	}
	defer file.Close()

	var vars []EnvVar
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) == 2 {
			key := strings.TrimSpace(parts[0])
			value := strings.TrimSpace(parts[1])
			value = strings.Trim(value, "\"'")
			// Reverse the escaping from WriteEnvFile: \\n → sentinel, \n → real newline, sentinel → \n.
			value = strings.ReplaceAll(value, `\\n`, "\x00ESCAPED_NEWLINE\x00")
			value = strings.ReplaceAll(value, `\n`, "\n")
			value = strings.ReplaceAll(value, "\x00ESCAPED_NEWLINE\x00", `\n`)
			vars = append(vars, EnvVar{Key: key, Value: value})
		}
	}

	return vars, scanner.Err()
}

// WriteEnvFile writes environment variables to a .env file.
func WriteEnvFile(path string, vars []EnvVar) error {
	var lines []string
	for _, v := range vars {
		// Escape literal \n first so it survives the round-trip, then escape real newlines.
		value := strings.ReplaceAll(v.Value, `\n`, `\\n`)
		value = strings.ReplaceAll(value, "\n", `\n`)
		if strings.ContainsAny(value, " \t\"'") {
			value = fmt.Sprintf("\"%s\"", strings.ReplaceAll(value, "\"", "\\\""))
		}
		lines = append(lines, fmt.Sprintf("%s=%s", v.Key, value))
	}

	content := strings.Join(lines, "\n")
	if len(lines) > 0 {
		content += "\n"
	}

	return os.WriteFile(path, []byte(content), 0600)
}

// MergeEnvFile reads the .env at path, applies updates (add or replace keys),
// and writes it back. Preserves ordering of existing keys; new keys are appended.
// If skipEmpty is true, update entries with empty values are ignored.
func MergeEnvFile(path string, updates map[string]string, skipEmpty bool) error {
	existing, err := ReadEnvFile(path)
	if err != nil {
		return fmt.Errorf("read .env: %w", err)
	}

	updated := make(map[string]bool, len(updates))
	var result []EnvVar
	for _, ev := range existing {
		if newVal, ok := updates[ev.Key]; ok && (!skipEmpty || newVal != "") {
			result = append(result, EnvVar{Key: ev.Key, Value: newVal})
			updated[ev.Key] = true
		} else {
			result = append(result, ev)
		}
	}
	for key, val := range updates {
		if !updated[key] && (!skipEmpty || val != "") {
			result = append(result, EnvVar{Key: key, Value: val})
		}
	}

	return WriteEnvFile(path, result)
}
