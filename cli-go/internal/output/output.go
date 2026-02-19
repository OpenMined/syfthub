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
	"golang.org/x/term"
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

// Grid layout utilities for ls-style output

// getTerminalWidth returns the terminal width, defaulting to 80 if unable to detect.
func getTerminalWidth() int {
	width, _, err := term.GetSize(int(os.Stdout.Fd()))
	if err != nil || width <= 0 {
		return 80 // sensible default
	}
	return width
}

// gridItem represents an item to display in the grid.
type gridItem struct {
	display string // the styled/colored string to display
	width   int    // the visual width (without ANSI codes)
}

// printGrid prints items in a grid layout like Unix ls command.
// Items are filled column-by-column (vertically) like ls does.
func printGrid(items []gridItem, padding int) {
	if len(items) == 0 {
		return
	}

	termWidth := getTerminalWidth()

	// Find the maximum item width
	maxWidth := 0
	for _, item := range items {
		if item.width > maxWidth {
			maxWidth = item.width
		}
	}

	// Calculate column width (item width + padding)
	colWidth := maxWidth + padding

	// Calculate number of columns that fit
	cols := termWidth / colWidth
	if cols < 1 {
		cols = 1
	}

	// Calculate number of rows needed
	rows := (len(items) + cols - 1) / cols

	// Print grid (fill columns vertically like ls)
	for row := 0; row < rows; row++ {
		for col := 0; col < cols; col++ {
			// Calculate index: fill vertically
			idx := col*rows + row
			if idx >= len(items) {
				continue
			}

			item := items[idx]

			// Print item with padding
			fmt.Print(item.display)

			// Add spacing to align columns (except last column)
			if col < cols-1 && idx+rows < len(items) {
				// Calculate how many spaces needed to reach column width
				spaces := colWidth - item.width
				if spaces > 0 {
					fmt.Print(strings.Repeat(" ", spaces))
				}
			}
		}
		fmt.Println()
	}
}

// printGridHorizontal prints items in a grid layout filling rows first.
// This is an alternative to the default vertical fill.
func printGridHorizontal(items []gridItem, padding int) {
	if len(items) == 0 {
		return
	}

	termWidth := getTerminalWidth()

	// Find the maximum item width
	maxWidth := 0
	for _, item := range items {
		if item.width > maxWidth {
			maxWidth = item.width
		}
	}

	// Calculate column width (item width + padding)
	colWidth := maxWidth + padding

	// Calculate number of columns that fit
	cols := termWidth / colWidth
	if cols < 1 {
		cols = 1
	}

	// Print grid (fill rows horizontally)
	for i, item := range items {
		fmt.Print(item.display)

		// Add spacing or newline
		if (i+1)%cols == 0 {
			fmt.Println()
		} else {
			spaces := colWidth - item.width
			if spaces > 0 {
				fmt.Print(strings.Repeat(" ", spaces))
			}
		}
	}

	// Final newline if needed
	if len(items)%cols != 0 {
		fmt.Println()
	}
}

// visualWidth returns the visual width of a string, ignoring ANSI escape codes.
func visualWidth(s string) int {
	return lipgloss.Width(s)
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

	// Sort owners alphabetically
	sort.Slice(owners, func(i, j int) bool {
		return owners[i].Username < owners[j].Username
	})

	// Build grid items
	items := make([]gridItem, 0, len(owners))
	for _, owner := range owners {
		// Directory-style name with trailing slash (like ls for directories)
		name := Cyan.Sprintf("%s/", owner.Username)

		// Build count indicator
		var counts []string
		if owner.ModelCount > 0 {
			counts = append(counts, fmt.Sprintf("%d", owner.ModelCount)+Magenta.Sprint("m"))
		}
		if owner.DataSourceCount > 0 {
			counts = append(counts, fmt.Sprintf("%d", owner.DataSourceCount)+Blue.Sprint("d"))
		}

		var display string
		if len(counts) > 0 {
			display = name + " " + Dim.Sprint("("+strings.Join(counts, ",")+")")
		} else {
			display = name
		}

		// Calculate visual width
		width := len(owner.Username) + 1 // +1 for the slash
		if len(counts) > 0 {
			// Add space + parens + counts
			countWidth := 3 // " ()"
			for i, c := range counts {
				if i > 0 {
					countWidth++ // comma
				}
				// Count digits + letter
				countWidth += len(fmt.Sprintf("%d", owner.ModelCount)) + 1
				_ = c
			}
			// Simplified: just measure the actual count string
			countStr := strings.Join(counts, ",")
			width += 3 + len(countStr) // " (" + counts + ")"
		}

		items = append(items, gridItem{
			display: display,
			width:   visualWidth(display),
		})
	}

	// Print using ls-style grid (vertical fill)
	printGrid(items, 2)
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

	// Build grid items
	items := make([]gridItem, 0, len(usernames))
	for _, username := range usernames {
		endpoints := users[username]

		// Count by type
		typeCounts := make(map[string]int)
		for _, ep := range endpoints {
			typeCounts[ep.Type]++
		}

		// Build count indicator
		var counts []string
		if count, ok := typeCounts["model"]; ok && count > 0 {
			counts = append(counts, fmt.Sprintf("%d", count)+Magenta.Sprint("m"))
		}
		if count, ok := typeCounts["data_source"]; ok && count > 0 {
			counts = append(counts, fmt.Sprintf("%d", count)+Blue.Sprint("d"))
		}
		if count, ok := typeCounts["model_data_source"]; ok && count > 0 {
			counts = append(counts, fmt.Sprintf("%d", count)+Yellow.Sprint("h"))
		}

		// Directory-style name with trailing slash
		name := Cyan.Sprintf("%s/", username)

		var display string
		if len(counts) > 0 {
			display = name + " " + Dim.Sprint("("+strings.Join(counts, ",")+")")
		} else {
			display = name
		}

		items = append(items, gridItem{
			display: display,
			width:   visualWidth(display),
		})
	}

	// Print using ls-style grid (vertical fill)
	printGrid(items, 2)
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

// PrintEndpointsGrid prints endpoints in a grid layout like ls.
func PrintEndpointsGrid(endpoints []EndpointInfo, username string) {
	if len(endpoints) == 0 {
		if username != "" {
			Dim.Printf("No endpoints found for '%s'\n", username)
		} else {
			Dim.Println("No endpoints found.")
		}
		return
	}

	// Print header like "username/" if provided
	if username != "" {
		Cyan.Printf("%s/\n", username)
	}

	// Sort by name (like ls does alphabetically)
	sort.Slice(endpoints, func(i, j int) bool {
		return endpoints[i].Name < endpoints[j].Name
	})

	// Build grid items
	items := make([]gridItem, 0, len(endpoints))
	for _, ep := range endpoints {
		// Use type-specific color for the name
		c := TypeColor(ep.Type)
		icon := TypeIcon(ep.Type)

		// Format: icon + name (like ls with icons)
		display := icon + " " + c.Sprint(ep.Name)

		items = append(items, gridItem{
			display: display,
			width:   visualWidth(display),
		})
	}

	// Print using ls-style grid (vertical fill)
	printGrid(items, 2)
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
