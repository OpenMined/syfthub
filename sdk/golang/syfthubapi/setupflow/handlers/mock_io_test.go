package handlers

import (
	"fmt"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// testIO is a shared mock SetupIO for handler tests.
// Configure the callback fields needed for each test; unconfigured methods use safe defaults.
type testIO struct {
	promptResponses []string
	promptIndex     int
	selectResponse  string
	statusMessages  []string
}

func (m *testIO) Prompt(msg string, opts setupflow.PromptOpts) (string, error) {
	if m.promptIndex >= len(m.promptResponses) {
		return "", fmt.Errorf("no more prompt responses")
	}
	val := m.promptResponses[m.promptIndex]
	m.promptIndex++
	return val, nil
}

func (m *testIO) Select(msg string, options []setupflow.SelectOption) (string, error) {
	return m.selectResponse, nil
}

func (m *testIO) Confirm(msg string) (bool, error) { return false, nil }
func (m *testIO) OpenBrowser(url string) error     { return nil }
func (m *testIO) Status(msg string)                { m.statusMessages = append(m.statusMessages, msg) }
func (m *testIO) Error(msg string)                 {}
