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
			vars = append(vars, EnvVar{Key: key, Value: value})
		}
	}

	return vars, scanner.Err()
}

// WriteEnvFile writes environment variables to a .env file.
func WriteEnvFile(path string, vars []EnvVar) error {
	var lines []string
	for _, v := range vars {
		value := v.Value
		if strings.ContainsAny(value, " \t\n\"'") {
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
