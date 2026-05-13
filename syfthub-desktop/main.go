package main

import (
	"embed"
	"fmt"
	"os"
	"os/exec"

	"github.com/openmined/syfthub-desktop-gui/internal/updater"
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

//go:embed build/appicon.png
var icon []byte

// preWailsBootstrap handles the Phase 3 post-update / rollback hooks
// before Wails is started. It runs the post-update cleanup if invoked
// with --post-update, then consults the boot guard to decide whether
// to roll back a failing install.
func preWailsBootstrap() {
	exePath, err := os.Executable()
	if err != nil {
		// Without an executable path we can't run rollback logic safely.
		return
	}

	// Post-update flag: clean up sibling .old binaries left over from
	// the previous swap. Strip the flag from os.Args so it doesn't trip
	// any other parser later.
	if len(os.Args) > 1 && os.Args[1] == updater.PostUpdateFlag {
		updater.PostUpdateCleanup(exePath)
		os.Args = append(os.Args[:1], os.Args[2:]...)
	}

	// Rollback check: if the most recent install is failing to boot,
	// restore the previous binary and exec it.
	dir, err := getSettingsDir()
	if err != nil {
		return
	}
	guard := updater.NewBootGuard(dir, exePath)
	if !guard.OnLaunch() {
		return
	}
	restored, rbErr := updater.PerformRollback(exePath)
	if rbErr != nil {
		fmt.Fprintln(os.Stderr, "auto-rollback skipped:", rbErr)
		return
	}
	cmd := exec.Command(restored)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "rollback process exited:", err)
	}
	os.Exit(0)
}

func main() {
	preWailsBootstrap()

	// Create an instance of the app structure
	app := NewApp()

	// Sidebar color: bg-card/30 over slate-900 background
	// slate-900 = RGB(15, 23, 42), slate-800 = RGB(30, 41, 59)
	// Effective color at 30% opacity ≈ RGB(20, 28, 47)
	sidebarColor := windows.RGB(20, 28, 47)
	sidebarColorInactive := windows.RGB(15, 23, 42) // Slightly darker when inactive

	// Create application with options
	err := wails.Run(&options.App{
		Title:           "SyftHub Desktop",
		Width:           1280,
		Height:          800,
		MinWidth:        800,
		MinHeight:       600,
		Frameless:       true,
		CSSDragProperty: "--wails-draggable",
		CSSDragValue:    "drag",
		// Enable Wails native file drop so dropped files arrive as absolute
		// paths via the "wails:file-drop" event. The dropzone element opts in
		// by setting style="--wails-drop-target: drop" on itself.
		DragAndDrop: &options.DragAndDrop{
			EnableFileDrop:  true,
			CSSDropProperty: "--wails-drop-target",
			CSSDropValue:    "drop",
		},
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
				Icon:    icon,
			},
		},
		// Linux: Limited title bar customization (controlled by window manager)
		Linux: &linux.Options{
			ProgramName: "SyftHub Desktop",
			Icon:        icon,
		},
	})

	if err != nil {
		println("Error:", err.Error())
	}
}
