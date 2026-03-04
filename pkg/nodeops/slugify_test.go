package nodeops

import "testing"

func TestSlugify(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"simple", "My Cool Model", "my-cool-model"},
		{"underscores", "data_source_one", "data-source-one"},
		{"special chars", "Hello, World! #1", "hello-world-1"},
		{"leading trailing", "  --spaces-- ", "spaces"},
		{"consecutive hyphens", "a---b", "a-b"},
		{"empty", "", ""},
		{"numbers", "model-42", "model-42"},
		{"already slug", "my-model", "my-model"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Slugify(tt.in)
			if got != tt.want {
				t.Errorf("Slugify(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

func TestSlugifyFilename(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"normal", "My Rate Limit Policy", "my-rate-limit-policy.yaml"},
		{"empty", "", "policy.yaml"},
		{"special", "!!!???", "policy.yaml"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := SlugifyFilename(tt.in)
			if got != tt.want {
				t.Errorf("SlugifyFilename(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}
