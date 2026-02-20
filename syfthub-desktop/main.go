package main

import (
	"embed"

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"github.com/wailsapp/wails/v2/pkg/options/linux"
	"github.com/wailsapp/wails/v2/pkg/options/mac"
	"github.com/wailsapp/wails/v2/pkg/options/windows"
)

// Version is set at build time via ldflags
var Version = "dev"

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	// Create an instance of the app structure
	app := NewApp()

	// Sidebar color: bg-card/30 over slate-900 background
	// slate-900 = RGB(15, 23, 42), slate-800 = RGB(30, 41, 59)
	// Effective color at 30% opacity ≈ RGB(20, 28, 47)
	sidebarColor := windows.RGB(20, 28, 47)
	sidebarColorInactive := windows.RGB(15, 23, 42) // Slightly darker when inactive

	// Create application with options
	err := wails.Run(&options.App{
		Title:     "SyftHub Desktop",
		Width:     1280,
		Height:    800,
		MinWidth:  800,
		MinHeight: 600,
		AssetServer: &assetserver.Options{
			Assets: assets,
		},
		BackgroundColour: &options.RGBA{R: 15, G: 23, B: 42, A: 1}, // slate-900
		OnStartup:        app.startup,
		OnShutdown:       app.shutdown,
		Bind: []interface{}{
			app,
		},
		// Windows: Custom title bar color to match sidebar
		Windows: &windows.Options{
			Theme: windows.Dark,
			CustomTheme: &windows.ThemeSettings{
				DarkModeTitleBar:          sidebarColor,
				DarkModeTitleBarInactive:  sidebarColorInactive,
				DarkModeTitleText:         windows.RGB(246, 248, 250), // slate-100
				DarkModeTitleTextInactive: windows.RGB(148, 163, 184), // slate-400
				DarkModeBorder:            sidebarColor,
				DarkModeBorderInactive:    sidebarColorInactive,
			},
		},
		// macOS: Transparent title bar that blends with app content
		Mac: &mac.Options{
			TitleBar: &mac.TitleBar{
				TitlebarAppearsTransparent: true,
				HideTitle:                  true,
				FullSizeContent:            true,
			},
			Appearance: mac.NSAppearanceNameDarkAqua,
			About: &mac.AboutInfo{
				Title:   "SyftHub Desktop",
				Message: "Manage your SyftHub endpoints\nVersion: " + Version,
			},
		},
		// Linux: Limited title bar customization (controlled by window manager)
		Linux: &linux.Options{
			ProgramName: "SyftHub Desktop",
		},
	})

	if err != nil {
		println("Error:", err.Error())
	}
}
