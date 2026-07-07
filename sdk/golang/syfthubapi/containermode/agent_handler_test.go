package containermode

import (
	"strings"
	"testing"
)

func TestParseSSEStream_BasicEvent(t *testing.T) {
	input := "event: agent.thinking\ndata: {\"content\":\"hello\"}\nid: 1\n\n"
	reader := strings.NewReader(input)

	var events []struct {
		eventType, data, id string
	}

	err := parseSSEStream(reader, func(eventType, data, id string) {
		events = append(events, struct{ eventType, data, id string }{eventType, data, id})
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].eventType != "agent.thinking" {
		t.Errorf("expected event type 'agent.thinking', got '%s'", events[0].eventType)
	}
	if events[0].data != `{"content":"hello"}` {
		t.Errorf("unexpected data: %s", events[0].data)
	}
	if events[0].id != "1" {
		t.Errorf("expected id '1', got '%s'", events[0].id)
	}
}

func TestParseSSEStream_MultiLineData(t *testing.T) {
	input := "event: message\ndata: line1\ndata: line2\ndata: line3\n\n"
	reader := strings.NewReader(input)

	var events []struct{ data string }

	parseSSEStream(reader, func(_, data, _ string) {
		events = append(events, struct{ data string }{data})
	})

	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].data != "line1\nline2\nline3" {
		t.Errorf("expected joined data, got: %q", events[0].data)
	}
}

func TestParseSSEStream_MultipleEvents(t *testing.T) {
	input := "event: a\ndata: first\n\nevent: b\ndata: second\n\n"
	reader := strings.NewReader(input)

	var types []string

	parseSSEStream(reader, func(eventType, _, _ string) {
		types = append(types, eventType)
	})

	if len(types) != 2 {
		t.Fatalf("expected 2 events, got %d", len(types))
	}
	if types[0] != "a" || types[1] != "b" {
		t.Errorf("unexpected types: %v", types)
	}
}

func TestParseSSEStream_CommentsIgnored(t *testing.T) {
	input := ": this is a comment\nevent: test\ndata: hello\n\n"
	reader := strings.NewReader(input)

	var events []struct{ eventType string }

	parseSSEStream(reader, func(eventType, _, _ string) {
		events = append(events, struct{ eventType string }{eventType})
	})

	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].eventType != "test" {
		t.Errorf("unexpected event type: %s", events[0].eventType)
	}
}

func TestParseSSEStream_TerminalEventStopsProcessing(t *testing.T) {
	input := "event: agent.thinking\ndata: think\n\nevent: agent.session_complete\ndata: done\n\nevent: should.not.reach\ndata: nope\n\n"
	reader := strings.NewReader(input)

	var types []string

	parseSSEStream(reader, func(eventType, _, _ string) {
		types = append(types, eventType)
	})

	if len(types) != 2 {
		t.Fatalf("expected 2 events (stopped at terminal), got %d: %v", len(types), types)
	}
	if types[1] != "agent.session_complete" {
		t.Errorf("expected terminal event, got: %s", types[1])
	}
}

func TestParseSSEStream_DefaultEventType(t *testing.T) {
	// No event: field should default to "message"
	input := "data: hello\n\n"
	reader := strings.NewReader(input)

	var eventType string

	parseSSEStream(reader, func(et, _, _ string) {
		eventType = et
	})

	if eventType != "message" {
		t.Errorf("expected default event type 'message', got '%s'", eventType)
	}
}

func TestParseSSEStream_LeadingSpaceRemoved(t *testing.T) {
	// SSE spec: one leading space after colon is removed
	input := "data: hello world\n\n"
	reader := strings.NewReader(input)

	var data string

	parseSSEStream(reader, func(_, d, _ string) {
		data = d
	})

	if data != "hello world" {
		t.Errorf("expected 'hello world', got %q", data)
	}
}
