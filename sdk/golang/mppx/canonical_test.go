package mppx

import "testing"

func TestCanonicalizeJSON(t *testing.T) {
	cases := []struct {
		name string
		in   any
		want string
	}{
		{"sorts keys", map[string]any{"b": 2, "a": 1}, `{"a":1,"b":2}`},
		{"sorts nested", map[string]any{
			"z": []any{3, map[string]any{"y": 1, "x": 2}},
			"a": "hello",
		}, `{"a":"hello","z":[3,{"x":2,"y":1}]}`},
		{"nil", nil, "null"},
		{"bool", true, "true"},
		{"float integer", 1.0, "1"},
		{"float fractional", 1.5, "1.5"},
		{"empty object", map[string]any{}, "{}"},
		{"empty array", []any{}, "[]"},
		{"string with quote", "a\"b", `"a\"b"`},
		{"unicode key", map[string]any{"é": 1, "a": 2}, `{"a":2,"é":1}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := CanonicalizeJSON(tc.in)
			if err != nil {
				t.Fatalf("err: %v", err)
			}
			if string(got) != tc.want {
				t.Fatalf("got %q want %q", got, tc.want)
			}
		})
	}
}

func TestCanonicalizeJSONOmitsUndefined(t *testing.T) {
	got, err := CanonicalizeJSON(map[string]any{
		"a": 1,
		"b": Undefined(),
		"c": 2,
	})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if string(got) != `{"a":1,"c":2}` {
		t.Fatalf("got %q", got)
	}
}
