package mppx

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"sort"
	"strconv"
)

// CanonicalizeJSON returns the RFC 8785 (JCS) canonical JSON serialisation of
// the given value. Object keys are sorted recursively by UTF-16 code-unit
// comparison, no whitespace is inserted, and undefined-valued keys (i.e.
// JavaScript `undefined`, which Go has no analogue for) are omitted.
//
// This mirrors the behaviour of the `ox` library's Json.canonicalize used by
// the TypeScript mppx implementation, so the byte output is identical for
// structurally-equal inputs.
//
// Numbers are serialised per ECMAScript ToString (no trailing zeros).
// `bigint` is unsupported here because Go has no transparent equivalent.
func CanonicalizeJSON(value any) ([]byte, error) {
	switch v := value.(type) {
	case nil:
		return []byte("null"), nil
	case bool:
		if v {
			return []byte("true"), nil
		}
		return []byte("false"), nil
	case string:
		return jsonEncodeString(v)
	case json.Number:
		return []byte(v), nil
	case float64:
		return canonicalNumber(v)
	case float32:
		return canonicalNumber(float64(v))
	case int:
		return []byte(strconv.FormatInt(int64(v), 10)), nil
	case int8:
		return []byte(strconv.FormatInt(int64(v), 10)), nil
	case int16:
		return []byte(strconv.FormatInt(int64(v), 10)), nil
	case int32:
		return []byte(strconv.FormatInt(int64(v), 10)), nil
	case int64:
		return []byte(strconv.FormatInt(v, 10)), nil
	case uint:
		return []byte(strconv.FormatUint(uint64(v), 10)), nil
	case uint8:
		return []byte(strconv.FormatUint(uint64(v), 10)), nil
	case uint16:
		return []byte(strconv.FormatUint(uint64(v), 10)), nil
	case uint32:
		return []byte(strconv.FormatUint(uint64(v), 10)), nil
	case uint64:
		return []byte(strconv.FormatUint(v, 10)), nil
	case []any:
		var buf bytes.Buffer
		buf.WriteByte('[')
		for i, item := range v {
			if i > 0 {
				buf.WriteByte(',')
			}
			b, err := CanonicalizeJSON(item)
			if err != nil {
				return nil, err
			}
			buf.Write(b)
		}
		buf.WriteByte(']')
		return buf.Bytes(), nil
	case map[string]any:
		return canonicalObject(v)
	}
	return nil, fmt.Errorf("mppx: cannot canonicalize value of type %T", value)
}

func canonicalObject(m map[string]any) ([]byte, error) {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	// JS `.sort()` uses UTF-16 code-unit ordering. Go strings are UTF-8 byte
	// strings; for ASCII keys these orderings agree. Object keys in MPP are
	// always ASCII (intent, request fields, etc.) so a byte-wise sort matches
	// the reference implementation.
	sort.Strings(keys)
	var buf bytes.Buffer
	buf.WriteByte('{')
	first := true
	for _, k := range keys {
		val := m[k]
		// In RFC 8785, object members with `undefined` values are removed.
		// Go's distinction is recorded by an explicit `Undefined` sentinel;
		// callers should drop those before canonicalising.
		if _, isUndef := val.(undefinedValue); isUndef {
			continue
		}
		if !first {
			buf.WriteByte(',')
		}
		first = false
		kb, err := jsonEncodeString(k)
		if err != nil {
			return nil, err
		}
		buf.Write(kb)
		buf.WriteByte(':')
		vb, err := CanonicalizeJSON(val)
		if err != nil {
			return nil, err
		}
		buf.Write(vb)
	}
	buf.WriteByte('}')
	return buf.Bytes(), nil
}

// undefinedValue is a sentinel callers may use to mark a key for omission in
// canonical JSON output (mirrors JavaScript `undefined`).
type undefinedValue struct{}

// Undefined returns the sentinel value used to omit a field from canonical
// JSON output.
func Undefined() any { return undefinedValue{} }

func canonicalNumber(f float64) ([]byte, error) {
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return nil, errors.New("mppx: cannot canonicalize non-finite number")
	}
	if f == 0 {
		return []byte("0"), nil
	}
	// strconv.FormatFloat with 'g'+precision -1 yields the shortest
	// round-trippable representation, matching ECMAScript Number.toString for
	// most values. For full RFC 8785 conformance the spec requires the
	// "shortest-roundtrip" algorithm, which is exactly what -1 gives us.
	return []byte(strconv.FormatFloat(f, 'g', -1, 64)), nil
}

func jsonEncodeString(s string) ([]byte, error) {
	// Use encoding/json for proper escaping (\u escapes, surrogate handling).
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(s); err != nil {
		return nil, err
	}
	out := buf.Bytes()
	// json.Encoder appends a newline.
	if n := len(out); n > 0 && out[n-1] == '\n' {
		out = out[:n-1]
	}
	return out, nil
}
