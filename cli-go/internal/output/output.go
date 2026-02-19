// Package output provides terminal output formatting helpers.
package output

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/lipgloss"
	"github.com/fatih/color"
	"github.com/olekukonko/tablewriter"
)

// Color helpers
var (
	Red     = color.New(color.FgRed, color.Bold)
	Green   = color.New(color.FgGreen, color.Bold)
	Yellow  = color.New(color.FgYellow, color.Bold)
	Blue    = color.New(color.FgBlue, color.Bold)
	Cyan    = color.New(color.FgCyan, color.Bold)
	Magenta = color.New(color.FgMagenta)
	Dim     = color.New(color.Faint)
)

// Lip Gloss styles for enhanced terminal output
var (
	// Card style for endpoint details
	cardStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("63")).
			Padding(1, 2).
			MarginTop(1).
			MarginBottom(1)

	// Title style for endpoint name
	titleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("212"))

	// Subtle text style
	subtleStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("241"))

	// Type badge styles
	modelBadge = lipgloss.NewStyle().
			Background(lipgloss.Color("62")).
			Foreground(lipgloss.Color("230")).
			Padding(0, 1).
			MarginRight(1)

	dataSourceBadge = lipgloss.NewStyle().
			Background(lipgloss.Color("33")).
			Foreground(lipgloss.Color("230")).
			Padding(0, 1).
			MarginRight(1)

	hybridBadge = lipgloss.NewStyle().
			Background(lipgloss.Color("214")).
			Foreground(lipgloss.Color("232")).
			Padding(0, 1).
			MarginRight(1)

	// Star style
	starStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("220"))

	// Version style
	versionStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("243")).
			Italic(true)
)

// Error prints an error message to stderr.
func Error(format string, args ...interface{}) {
	Red.Fprint(os.Stderr, "Error: ")
	fmt.Fprintf(os.Stderr, format+"\n", args...)
}

// Success prints a success message.
func Success(format string, args ...interface{}) {
	Green.Printf(format+"\n", args...)
}

// Warning prints a warning message.
func Warning(format string, args ...interface{}) {
	Yellow.Print("Warning: ")
	fmt.Printf(format+"\n", args...)
}

// Info prints an info message.
func Info(format string, args ...interface{}) {
	Blue.Print("Info: ")
	fmt.Printf(format+"\n", args...)
}

// JSON prints data as formatted JSON.
func JSON(data interface{}) {
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	encoder.Encode(data)
}

// StreamToken prints a token for streaming output without newline.
func StreamToken(token string) {
	fmt.Print(token)
}

// StreamDone prints a newline after streaming is complete.
func StreamDone() {
	fmt.Println()
}

// Table creates and returns a configured table writer.
func Table(headers []string) *tablewriter.Table {
	table := tablewriter.NewWriter(os.Stdout)
	table.SetHeader(headers)
	table.SetBorder(false)
	table.SetHeaderAlignment(tablewriter.ALIGN_LEFT)
	table.SetAlignment(tablewriter.ALIGN_LEFT)
	table.SetCenterSeparator("")
	table.SetColumnSeparator("  ")
	table.SetRowSeparator("")
	table.SetHeaderLine(false)
	table.SetTablePadding("  ")
	table.SetNoWhiteSpace(true)
	return table
}

// TableWithTitle creates a table with a title.
func TableWithTitle(title string, headers []string) *tablewriter.Table {
	fmt.Printf("%s\n", title)
	fmt.Println()
	return Table(headers)
}

// TypeIcon returns an icon for endpoint type.
func TypeIcon(endpointType string) string {
	switch endpointType {
	case "model":
		return Magenta.Sprint("⚡")
	case "data_source":
		return Blue.Sprint("📦")
	case "model_data_source":
		return Yellow.Sprint("🔀")
	default:
		return "📄"
	}
}

// TypeBadge returns a styled badge for endpoint type.
func TypeBadge(endpointType string) string {
	switch endpointType {
	case "model":
		return modelBadge.Render("model")
	case "data_source":
		return dataSourceBadge.Render("data")
	case "model_data_source":
		return hybridBadge.Render("hybrid")
	default:
		return endpointType
	}
}

// TypeColor returns a color function for endpoint type.
func TypeColor(endpointType string) *color.Color {
	switch endpointType {
	case "model":
		return Magenta
	case "data_source":
		return Blue
	case "model_data_source":
		return Yellow
	default:
		return color.New(color.FgWhite)
	}
}

// EndpointInfo represents endpoint information for display.
type EndpointInfo struct {
	Name        string
	Slug        string
	Type        string
	Version     string
	Stars       int
	Description string
	Owner       string
	Readme      string
}

// UserInfo represents user information for display.
type UserInfo struct {
	Username  string
	Endpoints []EndpointInfo
}

// OwnerInfo represents owner summary information for display.
type OwnerInfo struct {
	Username        string
	EndpointCount   int
	ModelCount      int
	DataSourceCount int
}

// PrintOwnersGrid prints owners in a grid layout like Unix ls.
func PrintOwnersGrid(owners []OwnerInfo) {
	if len(owners) == 0 {
		Dim.Println("No users found.")
		return
	}

	// Calculate column width
	maxWidth := 32
	columns := 3 // Approximate for typical terminal width

	// Build cells
	cells := make([]string, 0, len(owners))
	for _, owner := range owners {
		// Build badge with counts
		var badges []string
		if owner.ModelCount > 0 {
			badges = append(badges, Magenta.Sprintf("%dm", owner.ModelCount))
		}
		if owner.DataSourceCount > 0 {
			badges = append(badges, Blue.Sprintf("%dd", owner.DataSourceCount))
		}
		// Calculate hybrid count (total - models - data_sources)
		hybridCount := owner.EndpointCount - owner.ModelCount - owner.DataSourceCount
		if hybridCount > 0 {
			badges = append(badges, Yellow.Sprintf("%dh", hybridCount))
		}

		name := owner.Username
		if len(name) > maxWidth-10 {
			name = name[:maxWidth-12] + ".."
		}

		cell := fmt.Sprintf("%s %s", Cyan.Sprintf("%s/", name), Dim.Sprint(strings.Join(badges, " ")))
		cells = append(cells, cell)
	}

	// Print in grid
	for i, cell := range cells {
		fmt.Printf("%-32s", cell)
		if (i+1)%columns == 0 {
			fmt.Println()
		}
	}
	if len(cells)%columns != 0 {
		fmt.Println()
	}
}

// PrintOwnersTable prints owners in a table format.
func PrintOwnersTable(owners []OwnerInfo) {
	if len(owners) == 0 {
		Dim.Println("No users found.")
		return
	}

	table := TableWithTitle("Active Users", []string{"Username", "Endpoints", "Models", "Data Sources"})

	for _, owner := range owners {
		table.Append([]string{
			owner.Username,
			fmt.Sprintf("%d", owner.EndpointCount),
			fmt.Sprintf("%d", owner.ModelCount),
			fmt.Sprintf("%d", owner.DataSourceCount),
		})
	}

	table.Render()
}

// PrintUsersGrid prints users in a grid layout like Unix ls.
func PrintUsersGrid(users map[string][]EndpointInfo) {
	if len(users) == 0 {
		Dim.Println("No users found.")
		return
	}

	// Sort usernames
	usernames := make([]string, 0, len(users))
	for username := range users {
		usernames = append(usernames, username)
	}
	sort.Strings(usernames)

	// Calculate column width
	maxWidth := 32
	columns := 3 // Approximate for typical terminal width

	// Build cells
	cells := make([]string, 0, len(usernames))
	for _, username := range usernames {
		endpoints := users[username]

		// Count by type
		typeCounts := make(map[string]int)
		for _, ep := range endpoints {
			typeCounts[ep.Type]++
		}

		// Build badge
		var badges []string
		if count, ok := typeCounts["model"]; ok {
			badges = append(badges, Magenta.Sprintf("%dm", count))
		}
		if count, ok := typeCounts["data_source"]; ok {
			badges = append(badges, Blue.Sprintf("%dd", count))
		}
		if count, ok := typeCounts["model_data_source"]; ok {
			badges = append(badges, Yellow.Sprintf("%dh", count))
		}

		name := username
		if len(name) > maxWidth-10 {
			name = name[:maxWidth-12] + ".."
		}

		cell := fmt.Sprintf("%s %s", Cyan.Sprintf("%s/", name), Dim.Sprint(strings.Join(badges, " ")))
		cells = append(cells, cell)
	}

	// Print in grid
	for i, cell := range cells {
		fmt.Printf("%-32s", cell)
		if (i+1)%columns == 0 {
			fmt.Println()
		}
	}
	if len(cells)%columns != 0 {
		fmt.Println()
	}
}

// PrintUsersTable prints users in a table format.
func PrintUsersTable(users map[string][]EndpointInfo) {
	if len(users) == 0 {
		Dim.Println("No users found.")
		return
	}

	table := TableWithTitle("Active Users", []string{"Username", "Endpoints", "Types"})

	// Sort usernames
	usernames := make([]string, 0, len(users))
	for username := range users {
		usernames = append(usernames, username)
	}
	sort.Strings(usernames)

	for _, username := range usernames {
		endpoints := users[username]

		// Get unique types
		types := make(map[string]bool)
		for _, ep := range endpoints {
			types[ep.Type] = true
		}

		typeList := make([]string, 0, len(types))
		for t := range types {
			typeList = append(typeList, t)
		}
		sort.Strings(typeList)

		table.Append([]string{
			username,
			fmt.Sprintf("%d", len(endpoints)),
			strings.Join(typeList, ", "),
		})
	}

	table.Render()
}

// PrintEndpointsGrid prints endpoints in a grid layout.
func PrintEndpointsGrid(endpoints []EndpointInfo, username string) {
	if len(endpoints) == 0 {
		if username != "" {
			Dim.Printf("No endpoints found for '%s'\n", username)
		} else {
			Dim.Println("No endpoints found.")
		}
		return
	}

	if username != "" {
		Cyan.Printf("%s/\n", username)
		fmt.Println()
	}

	// Sort by type then name
	sort.Slice(endpoints, func(i, j int) bool {
		if endpoints[i].Type != endpoints[j].Type {
			return endpoints[i].Type < endpoints[j].Type
		}
		return endpoints[i].Name < endpoints[j].Name
	})

	// Build cells
	maxWidth := 28
	columns := 3

	for i, ep := range endpoints {
		icon := TypeIcon(ep.Type)
		c := TypeColor(ep.Type)

		name := ep.Name
		if len(name) > maxWidth {
			name = name[:maxWidth-2] + ".."
		}

		fmt.Printf("%s %-28s", icon, c.Sprint(name))
		if (i+1)%columns == 0 {
			fmt.Println()
		}
	}
	if len(endpoints)%columns != 0 {
		fmt.Println()
	}
}

// PrintEndpointsTable prints endpoints in a table format.
func PrintEndpointsTable(endpoints []EndpointInfo, username string) {
	if len(endpoints) == 0 {
		if username != "" {
			Dim.Printf("No endpoints found for '%s'\n", username)
		} else {
			Dim.Println("No endpoints found.")
		}
		return
	}

	title := "Endpoints"
	if username != "" {
		title = fmt.Sprintf("Endpoints for %s", username)
	}

	table := TableWithTitle(title, []string{"Name", "Type", "Version", "Stars", "Description"})

	for _, ep := range endpoints {
		description := ep.Description
		if len(description) > 40 {
			description = description[:37] + "..."
		}

		table.Append([]string{
			ep.Name,
			ep.Type,
			ep.Version,
			fmt.Sprintf("%d", ep.Stars),
			description,
		})
	}

	table.Render()
}

// PrintEndpointDetail prints detailed information about an endpoint.
func PrintEndpointDetail(ep EndpointInfo) {
	// Build the card content
	var content strings.Builder

	// Title: owner/name
	title := titleStyle.Render(fmt.Sprintf("%s/%s", ep.Owner, ep.Name))
	content.WriteString(title)
	content.WriteString("\n")

	// Type badge and version
	badge := TypeBadge(ep.Type)
	version := versionStyle.Render(fmt.Sprintf("v%s", ep.Version))
	stars := starStyle.Render(fmt.Sprintf("★ %d", ep.Stars))

	content.WriteString(fmt.Sprintf("%s  %s  %s\n", badge, version, stars))

	// Description
	if ep.Description != "" {
		content.WriteString("\n")
		content.WriteString(subtleStyle.Render(ep.Description))
	}

	// Render the card
	fmt.Print(cardStyle.Render(content.String()))

	// README with Glamour markdown rendering
	if ep.Readme != "" {
		fmt.Println()

		// Create glamour renderer with auto style detection
		renderer, err := glamour.NewTermRenderer(
			glamour.WithAutoStyle(),
			glamour.WithWordWrap(80),
		)
		if err != nil {
			// Fallback to plain text if glamour fails
			fmt.Println("─── README ───")
			fmt.Println(ep.Readme)
			return
		}

		rendered, err := renderer.Render(ep.Readme)
		if err != nil {
			// Fallback to plain text
			fmt.Println("─── README ───")
			fmt.Println(ep.Readme)
			return
		}

		fmt.Print(rendered)
	}
}

// AliasInfo represents an infrastructure alias for display.
type AliasInfo struct {
	Name      string
	URL       string
	IsDefault bool
}

// PrintAliasesTable prints a table of aliases.
func PrintAliasesTable(aliases []AliasInfo, aliasType string) {
	if len(aliases) == 0 {
		Dim.Printf("No %s aliases configured.\n", strings.ToLower(aliasType))
		return
	}

	table := TableWithTitle(aliasType+" Aliases", []string{"Alias", "URL", "Default"})

	for _, alias := range aliases {
		def := ""
		if alias.IsDefault {
			def = "Yes"
		}
		table.Append([]string{alias.Name, alias.URL, def})
	}

	table.Render()
}

// ConfigValue represents a config key-value pair for display.
type ConfigValue struct {
	Key   string
	Value string
}

// PrintConfigTable prints configuration as a table.
func PrintConfigTable(values []ConfigValue) {
	table := TableWithTitle("Configuration", []string{"Key", "Value"})

	for _, v := range values {
		table.Append([]string{v.Key, v.Value})
	}

	table.Render()
}

// Truncate truncates a string to maxLen, adding "..." if truncated.
func Truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	if maxLen <= 3 {
		return s[:maxLen]
	}
	return s[:maxLen-3] + "..."
}

// MaskToken masks a token for display, showing only first 8 chars.
func MaskToken(token string) string {
	if token == "" {
		return Dim.Sprint("not set")
	}
	if len(token) > 8 {
		return token[:8] + "..."
	}
	return "***"
}
