package nodeops

import "strings"

// Slugify converts a display name to a URL-safe slug.
// E.g., "My Cool Model" -> "my-cool-model"
func Slugify(name string) string {
	slug := strings.ToLower(name)
	slug = strings.ReplaceAll(slug, " ", "-")
	slug = strings.ReplaceAll(slug, "_", "-")

	var result strings.Builder
	for _, r := range slug {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' {
			result.WriteRune(r)
		}
	}
	slug = result.String()

	for strings.Contains(slug, "--") {
		slug = strings.ReplaceAll(slug, "--", "-")
	}
	slug = strings.Trim(slug, "-")

	return slug
}

// SlugifyFilename converts a name to a valid YAML filename.
// E.g., "My Rate Limit Policy" -> "my-rate-limit-policy.yaml"
func SlugifyFilename(name string) string {
	slug := Slugify(name)
	if slug == "" {
		slug = "policy"
	}
	return slug + ".yaml"
}
