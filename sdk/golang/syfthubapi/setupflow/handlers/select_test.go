package handlers

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

func TestSelect_DynamicOptions(t *testing.T) {
	io := &testIO{selectResponse: "folder-123"}
	ctx := &setupflow.SetupContext{
		IO: io,
		StepOutputs: map[string]*setupflow.StepResult{
			"list_api": {
				Response: json.RawMessage(`{"files":[{"id":"folder-123","name":"My Folder"},{"id":"folder-456","name":"Other Folder"}]}`),
			},
		},
	}

	h := &SelectHandler{}
	step := &nodeops.SetupStep{
		ID:   "pick",
		Name: "Pick Folder",
		Select: &nodeops.SelectConfig{
			OptionsFrom: &nodeops.OptionsFromConfig{
				StepID:     "list_api",
				Path:       "files",
				ValueField: "id",
				LabelField: "name",
			},
		},
	}

	result, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Value != "folder-123" {
		t.Errorf("expected 'folder-123', got '%s'", result.Value)
	}
}

func TestSelect_DynamicOptions_EmptyArray(t *testing.T) {
	io := &testIO{}
	ctx := &setupflow.SetupContext{
		IO: io,
		StepOutputs: map[string]*setupflow.StepResult{
			"list_api": {
				Response: json.RawMessage(`{"files":[]}`),
			},
		},
	}

	h := &SelectHandler{}
	step := &nodeops.SetupStep{
		ID:   "pick",
		Name: "Pick",
		Select: &nodeops.SelectConfig{
			OptionsFrom: &nodeops.OptionsFromConfig{
				StepID:     "list_api",
				Path:       "files",
				ValueField: "id",
				LabelField: "name",
			},
		},
	}

	_, err := h.Execute(step, ctx)
	if err == nil {
		t.Fatal("expected error for empty options")
	}
}

func TestSelect_DynamicOptions_MissingStep(t *testing.T) {
	io := &testIO{}
	ctx := &setupflow.SetupContext{
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	h := &SelectHandler{}
	step := &nodeops.SetupStep{
		ID:   "pick",
		Name: "Pick",
		Select: &nodeops.SelectConfig{
			OptionsFrom: &nodeops.OptionsFromConfig{
				StepID:     "nonexistent",
				Path:       "data",
				ValueField: "id",
				LabelField: "name",
			},
		},
	}

	_, err := h.Execute(step, ctx)
	if err == nil {
		t.Fatal("expected error for missing step")
	}
	if !strings.Contains(err.Error(), "not completed") {
		t.Errorf("unexpected error: %v", err)
	}
}
