package setupflow

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

var templatePattern = regexp.MustCompile(`\{\{([^}]+)\}\}`)

// ResolveTemplate replaces {{...}} placeholders in a string with values from context.
//
// Supported template variables:
//
//	{{steps.<step_id>.value}}                — primary output of a step
//	{{steps.<step_id>.outputs.<env_key>}}    — named output of a step
//	{{steps.<step_id>.response.<json.path>}} — JSON path into HTTP response
//	{{context.hub_url}}                      — hub URL
//	{{context.endpoint_slug}}                — endpoint slug
//	{{context.username}}                     — authenticated username
//	{{env.<VAR_NAME>}}                       — system environment variable
//
// Returns the resolved string, or error if a required reference cannot be resolved.
func ResolveTemplate(tmpl string, ctx *SetupContext) (string, error) {
	if !strings.Contains(tmpl, "{{") {
		return tmpl, nil
	}

	var resolveErr error
	result := templatePattern.ReplaceAllStringFunc(tmpl, func(match string) string {
		if resolveErr != nil {
			return match
		}

		// Extract content between {{ and }}
		inner := strings.TrimSpace(match[2 : len(match)-2])
		parts := strings.SplitN(inner, ".", 2)
		if len(parts) < 2 {
			resolveErr = fmt.Errorf("invalid template reference: %s", match)
			return match
		}

		namespace := parts[0]
		rest := parts[1]

		switch namespace {
		case "steps":
			val, err := resolveStepRef(rest, ctx)
			if err != nil {
				resolveErr = err
				return match
			}
			return val

		case "context":
			val, err := resolveContextRef(rest, ctx)
			if err != nil {
				resolveErr = err
				return match
			}
			return val

		case "env":
			return resolveEnvRef(rest)

		default:
			resolveErr = fmt.Errorf("unknown template namespace '%s' in %s", namespace, match)
			return match
		}
	})

	if resolveErr != nil {
		return "", resolveErr
	}
	return result, nil
}

// resolveStepRef resolves a steps.<step_id>.<property> reference.
func resolveStepRef(rest string, ctx *SetupContext) (string, error) {
	parts := strings.SplitN(rest, ".", 2)
	stepID := parts[0]

	result, ok := ctx.StepOutputs[stepID]
	if !ok {
		return "", fmt.Errorf("step '%s' has not completed yet", stepID)
	}

	if len(parts) == 1 {
		return result.Value, nil
	}

	property := parts[1]

	if property == "value" {
		return result.Value, nil
	}

	if strings.HasPrefix(property, "outputs.") {
		envKey := strings.TrimPrefix(property, "outputs.")
		if val, ok := result.Outputs[envKey]; ok {
			return val, nil
		}
		return "", fmt.Errorf("step '%s' has no output '%s'", stepID, envKey)
	}

	if strings.HasPrefix(property, "response.") {
		jsonPath := strings.TrimPrefix(property, "response.")
		if result.Response == nil {
			return "", fmt.Errorf("step '%s' has no response", stepID)
		}
		return extractJSONPath(result.Response, jsonPath)
	}

	return "", fmt.Errorf("unknown step property '%s'", property)
}

// resolveContextRef resolves a context.<name> reference.
func resolveContextRef(name string, ctx *SetupContext) (string, error) {
	switch name {
	case "hub_url":
		return ctx.HubURL, nil
	case "endpoint_slug":
		return ctx.Slug, nil
	case "username":
		return ctx.Username, nil
	default:
		return "", fmt.Errorf("unknown context variable '%s'", name)
	}
}

// resolveEnvRef resolves an env.<VAR_NAME> reference from system environment.
func resolveEnvRef(name string) string {
	// Use os.Getenv but we import only what we need
	// Avoid importing os just for this — use a simple lookup
	// Actually we do need os.Getenv
	return getEnvVar(name)
}

// getEnvVar wraps os.Getenv. Separated for testability.
var getEnvVar = os.Getenv

// ResolveStringMap resolves templates in all values of a map.
func ResolveStringMap(m map[string]string, ctx *SetupContext) (map[string]string, error) {
	if m == nil {
		return nil, nil
	}
	result := make(map[string]string, len(m))
	for k, v := range m {
		resolved, err := ResolveTemplate(v, ctx)
		if err != nil {
			return nil, fmt.Errorf("key '%s': %w", k, err)
		}
		result[k] = resolved
	}
	return result, nil
}

// ResolveStep returns a deep copy of the step with all string fields template-resolved.
func ResolveStep(step *nodeops.SetupStep, ctx *SetupContext) (*nodeops.SetupStep, error) {
	// Create a shallow copy
	resolved := *step

	// Resolve type-specific configs
	switch step.Type {
	case "prompt":
		if step.Prompt != nil {
			p := *step.Prompt
			msg, err := ResolveTemplate(p.Message, ctx)
			if err != nil {
				return nil, err
			}
			p.Message = msg
			if p.Default != "" {
				def, err := ResolveTemplate(p.Default, ctx)
				if err != nil {
					return nil, err
				}
				p.Default = def
			}
			resolved.Prompt = &p
		}
	case "select":
		if step.Select != nil {
			s := *step.Select
			if s.Message != "" {
				msg, err := ResolveTemplate(s.Message, ctx)
				if err != nil {
					return nil, err
				}
				s.Message = msg
			}
			resolved.Select = &s
		}
	case "http":
		if step.HTTP != nil {
			h := *step.HTTP
			url, err := ResolveTemplate(h.URL, ctx)
			if err != nil {
				return nil, err
			}
			h.URL = url
			if h.Headers != nil {
				headers, err := ResolveStringMap(h.Headers, ctx)
				if err != nil {
					return nil, err
				}
				h.Headers = headers
			}
			if h.Query != nil {
				query, err := ResolveStringMap(h.Query, ctx)
				if err != nil {
					return nil, err
				}
				h.Query = query
			}
			if h.Body != "" {
				body, err := ResolveTemplate(h.Body, ctx)
				if err != nil {
					return nil, err
				}
				h.Body = body
			}
			resolved.HTTP = &h
		}
	case "template":
		if step.Template != nil {
			tmpl := *step.Template
			val, err := ResolveTemplate(tmpl.Value, ctx)
			if err != nil {
				return nil, err
			}
			tmpl.Value = val
			resolved.Template = &tmpl
		}
	case "oauth2":
		if step.OAuth2 != nil {
			o := *step.OAuth2
			if o.ClientID != "" {
				cid, err := ResolveTemplate(o.ClientID, ctx)
				if err != nil {
					return nil, err
				}
				o.ClientID = cid
			}
			if o.ClientSecret != "" {
				cs, err := ResolveTemplate(o.ClientSecret, ctx)
				if err != nil {
					return nil, err
				}
				o.ClientSecret = cs
			}
			resolved.OAuth2 = &o
		}
	}

	return &resolved, nil
}

// extractJSONPath navigates a JSON value by dot-separated path.
// Supports dot notation and array indexing: "result.items[0].name"
func extractJSONPath(data json.RawMessage, path string) (string, error) {
	var current interface{}
	if err := json.Unmarshal(data, &current); err != nil {
		return "", fmt.Errorf("failed to parse JSON: %w", err)
	}

	segments := splitJSONPath(path)

	for _, seg := range segments {
		switch v := current.(type) {
		case map[string]interface{}:
			// Check for array index: "items[0]"
			key, idx, hasIdx := parseArrayIndex(seg)
			if hasIdx {
				arrVal, ok := v[key]
				if !ok {
					return "", fmt.Errorf("key '%s' not found in JSON", key)
				}
				arr, ok := arrVal.([]interface{})
				if !ok {
					return "", fmt.Errorf("'%s' is not an array", key)
				}
				if idx < 0 || idx >= len(arr) {
					return "", fmt.Errorf("array index %d out of bounds for '%s' (length %d)", idx, key, len(arr))
				}
				current = arr[idx]
			} else {
				val, ok := v[seg]
				if !ok {
					return "", fmt.Errorf("key '%s' not found in JSON", seg)
				}
				current = val
			}
		case []interface{}:
			// Direct array index: "[0]"
			_, idx, hasIdx := parseArrayIndex(seg)
			if !hasIdx {
				return "", fmt.Errorf("expected array index, got '%s'", seg)
			}
			if idx < 0 || idx >= len(v) {
				return "", fmt.Errorf("array index %d out of bounds (length %d)", idx, len(v))
			}
			current = v[idx]
		default:
			return "", fmt.Errorf("cannot navigate into %T with key '%s'", current, seg)
		}
	}

	// Convert final value to string
	switch v := current.(type) {
	case string:
		return v, nil
	case float64:
		if v == float64(int64(v)) {
			return strconv.FormatInt(int64(v), 10), nil
		}
		return strconv.FormatFloat(v, 'f', -1, 64), nil
	case bool:
		return strconv.FormatBool(v), nil
	case nil:
		return "", nil
	default:
		// For objects/arrays, return JSON representation
		b, err := json.Marshal(v)
		if err != nil {
			return "", err
		}
		return string(b), nil
	}
}

// splitJSONPath splits a dot-separated JSON path while respecting array indices.
func splitJSONPath(path string) []string {
	return strings.Split(path, ".")
}

// parseArrayIndex checks if a segment contains an array index like "items[0]".
// Returns (key, index, hasIndex).
func parseArrayIndex(seg string) (string, int, bool) {
	openIdx := strings.Index(seg, "[")
	closeIdx := strings.Index(seg, "]")
	if openIdx == -1 || closeIdx == -1 || closeIdx <= openIdx {
		return seg, 0, false
	}

	key := seg[:openIdx]
	idxStr := seg[openIdx+1 : closeIdx]
	idx, err := strconv.Atoi(idxStr)
	if err != nil {
		return seg, 0, false
	}

	return key, idx, true
}

// resolveStepLocalTemplate resolves templates that refer to the current step's result.
// Used for output templates like "{{response.access_token}}" which are shorthand
// for the step's own response.
func resolveStepLocalTemplate(tmpl string, result *StepResult) (string, error) {
	if !strings.Contains(tmpl, "{{") {
		return tmpl, nil
	}

	var resolveErr error
	resolved := templatePattern.ReplaceAllStringFunc(tmpl, func(match string) string {
		if resolveErr != nil {
			return match
		}

		inner := strings.TrimSpace(match[2 : len(match)-2])

		if inner == "value" {
			return result.Value
		}

		if strings.HasPrefix(inner, "response.") {
			path := strings.TrimPrefix(inner, "response.")
			if result.Response == nil {
				resolveErr = fmt.Errorf("no response data available")
				return match
			}
			val, err := extractJSONPath(result.Response, path)
			if err != nil {
				resolveErr = err
				return match
			}
			return val
		}

		if strings.HasPrefix(inner, "outputs.") {
			key := strings.TrimPrefix(inner, "outputs.")
			if val, ok := result.Outputs[key]; ok {
				return val
			}
			resolveErr = fmt.Errorf("no output '%s' available", key)
			return match
		}

		resolveErr = fmt.Errorf("cannot resolve local template '%s'", inner)
		return match
	})

	if resolveErr != nil {
		return "", resolveErr
	}
	return resolved, nil
}
