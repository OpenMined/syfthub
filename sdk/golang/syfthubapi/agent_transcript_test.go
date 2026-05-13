package syfthubapi

import (
	"context"
	"encoding/json"
	"testing"
)

// TestAgentSessionTranscript exercises every transcript-recording rule the
// SDK guarantees: construction-time seeding, dedup of a duplicate prompt,
// user_message capture, control-signal exclusion, agent.message capture,
// and exclusion of non-conversational outbound event types.
func TestAgentSessionTranscript(t *testing.T) {
	t.Run("seeds from prompt only", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{
			ID:     "s1",
			Prompt: "hello",
		})
		tr := s.Transcript()
		if len(tr) != 1 || tr[0].Role != "user" || tr[0].Content != "hello" {
			t.Fatalf("unexpected transcript: %#v", tr)
		}
	})

	t.Run("seeds from history + prompt", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{
			ID:     "s2",
			Prompt: "now what?",
			Messages: []Message{
				{Role: "user", Content: "first"},
				{Role: "assistant", Content: "ok"},
			},
		})
		tr := s.Transcript()
		if len(tr) != 3 {
			t.Fatalf("len = %d, want 3: %#v", len(tr), tr)
		}
		if tr[2].Role != "user" || tr[2].Content != "now what?" {
			t.Errorf("prompt entry = %#v", tr[2])
		}
	})

	t.Run("dedups prompt that matches trailing history user message", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{
			ID:     "s3",
			Prompt: "same",
			Messages: []Message{
				{Role: "assistant", Content: "prior"},
				{Role: "user", Content: "same"},
			},
		})
		tr := s.Transcript()
		if len(tr) != 2 {
			t.Fatalf("dedup failed, got %d entries: %#v", len(tr), tr)
		}
	})

	t.Run("captures user_message via DeliverMessage and excludes control types", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{ID: "s4", Prompt: "start"})

		// Drain recvCh in the background so DeliverMessage's bounded buffer
		// doesn't fill (handler-side simulation).
		drained := make(chan struct{})
		go func() {
			defer close(drained)
			for range 4 {
				if _, err := s.Receive(); err != nil {
					return
				}
			}
		}()

		if !s.DeliverMessage(UserMessage{Type: "user_message", Content: "follow-up 1"}) {
			t.Fatal("DeliverMessage(user_message) failed")
		}
		if !s.DeliverMessage(UserMessage{Type: "user_confirm", ToolCallID: "tc-1"}) {
			t.Fatal("DeliverMessage(user_confirm) failed")
		}
		if !s.DeliverMessage(UserMessage{Type: "user_deny", Reason: "nope"}) {
			t.Fatal("DeliverMessage(user_deny) failed")
		}
		if !s.DeliverMessage(UserMessage{Type: "user_message", Content: "follow-up 2"}) {
			t.Fatal("DeliverMessage(user_message #2) failed")
		}

		<-drained

		tr := s.Transcript()
		if len(tr) != 3 {
			t.Fatalf("len = %d, want 3 (prompt + 2 follow-ups): %#v", len(tr), tr)
		}
		if tr[1].Content != "follow-up 1" || tr[2].Content != "follow-up 2" {
			t.Errorf("unexpected follow-ups: %#v", tr)
		}
	})

	t.Run("skips empty user_message content", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{ID: "s5", Prompt: "p"})
		done := make(chan struct{})
		go func() { defer close(done); _, _ = s.Receive() }()
		s.DeliverMessage(UserMessage{Type: "user_message", Content: ""})
		<-done
		if got := len(s.Transcript()); got != 1 {
			t.Errorf("empty content should not be recorded; got %d entries", got)
		}
	})

	t.Run("captures agent.message via Send and excludes other event types", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{ID: "s6", Prompt: "go"})

		drained := make(chan struct{})
		go func() {
			defer close(drained)
			count := 0
			for range s.SendCh() {
				count++
				if count == 4 {
					return
				}
			}
		}()

		if err := s.SendMessage("first assistant reply"); err != nil {
			t.Fatal(err)
		}
		if err := s.SendToken("partial"); err != nil {
			t.Fatal(err)
		}
		if err := s.SendThinking("…"); err != nil {
			t.Fatal(err)
		}
		if err := s.SendMessage("second assistant reply"); err != nil {
			t.Fatal(err)
		}

		<-drained

		tr := s.Transcript()
		if len(tr) != 3 {
			t.Fatalf("len = %d, want 3 (prompt + 2 assistant): %#v", len(tr), tr)
		}
		if tr[1].Role != "assistant" || tr[1].Content != "first assistant reply" {
			t.Errorf("tr[1] = %#v", tr[1])
		}
		if tr[2].Role != "assistant" || tr[2].Content != "second assistant reply" {
			t.Errorf("tr[2] = %#v", tr[2])
		}
	})

	t.Run("records via direct Send with EventTypeAgentMessage", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{ID: "s7", Prompt: "p"})
		done := make(chan struct{})
		go func() { defer close(done); <-s.SendCh() }()
		data, _ := json.Marshal(map[string]any{"content": "direct"})
		if err := s.Send(AgentEventPayload{EventType: EventTypeAgentMessage, Data: data}); err != nil {
			t.Fatal(err)
		}
		<-done
		tr := s.Transcript()
		if len(tr) != 2 || tr[1].Content != "direct" {
			t.Errorf("direct Send not recorded: %#v", tr)
		}
	})

	t.Run("Transcript returns defensive copy", func(t *testing.T) {
		s := NewAgentSession(context.Background(), AgentSessionParams{ID: "s8", Prompt: "p"})
		first := s.Transcript()
		first[0].Content = "MUTATED"
		second := s.Transcript()
		if second[0].Content != "p" {
			t.Errorf("Transcript() did not return a defensive copy: %#v", second)
		}
	})
}
