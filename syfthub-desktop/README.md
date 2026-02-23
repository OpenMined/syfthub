# SyftHub Desktop GUI

A desktop GUI for managing SyftHub local endpoints, built with Wails, React, and Go.

## Features

- **Dashboard UI** - View and manage local endpoints
- **Service Control** - Start/stop the SyftHub service
- **Live Status** - Real-time state updates via Go events
- **Endpoint Discovery** - Automatic loading from `endpoints/` directory
- **Embedded Python** - Auto-downloads Python 3.13.1 on first run

## Tech Stack

- **[Wails v2.11.0](https://wails.io/)** - Desktop apps with Go + Web frontend
- **[React 18.3](https://react.dev/)** - React with TypeScript
- **[Tailwind CSS v4](https://tailwindcss.com/)** - Latest Tailwind with Vite plugin
- **[shadcn/ui](https://ui.shadcn.com/)** - Accessible component library
- **Go 1.23+** - Backend with embedded Python runtime

## Prerequisites

### Linux (Ubuntu 24.04+)

```bash
# Install Wails CLI
go install github.com/wailsapp/wails/v2/cmd/wails@latest

# Install GTK and WebKit dependencies
sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev

# Verify installation
wails doctor
```

### Windows

```bash
# Install Wails CLI
go install github.com/wailsapp/wails/v2/cmd/wails@latest

# WebView2 is included in Windows 10/11
wails doctor
```

### macOS

```bash
# Install Xcode command line tools
xcode-select --install

# Install Wails CLI
go install github.com/wailsapp/wails/v2/cmd/wails@latest

wails doctor
```

## Development

Run with hot reload:

```bash
# Linux (Ubuntu 24.04+)
make dev

# Or directly
wails dev -tags webkit2_41
```

The frontend dev server runs at http://localhost:5173 with Vite HMR.

## Building

```bash
# Build for current platform
make build

# Cross-compile for Windows (from Linux)
make build-windows

# See all targets
make help
```

Built applications are in `build/bin/`.

## Configuration

Create a `.env` file in the same directory as the executable:

```env
# SyftHub API connection
SYFTHUB_URL=https://api.syfthub.com
SYFTHUB_API_KEY=syft_pat_xxx

# Space configuration
# For tunnel mode: SPACE_URL=tunneling:your-username
# For HTTP mode: SPACE_URL=http://localhost:8001
SPACE_URL=tunneling:demo-user

# Optional settings
ENDPOINTS_PATH=./endpoints
LOG_LEVEL=INFO
WATCH_ENABLED=true
```

## Project Structure

```
syfthub-desktop-gui/
├── main.go              # Wails entry point
├── app.go               # Go binding layer (thread-safe state management)
├── types.go             # DTO types for frontend
├── internal/
│   └── app/             # Core application logic (shared with CLI)
├── frontend/
│   ├── src/
│   │   ├── App.tsx      # Dashboard UI
│   │   ├── hooks/
│   │   │   └── useApp.ts  # React hook for Go communication
│   │   └── components/ui/ # shadcn/ui components
│   └── wailsjs/         # Auto-generated Go bindings
├── build/bin/           # Built executables
└── Makefile             # Build targets
```

## Architecture

The GUI uses a **Facade pattern** where `app.go` wraps the complex `internal/app` subsystem:

```
┌─────────────────────┐     Events      ┌─────────────────────┐
│   React Frontend    │◄───────────────►│      app.go         │
│   (useApp hook)     │                 │   (Wails bindings)  │
└─────────────────────┘     Methods     └─────────────────────┘
                                               │
                                               ▼
                                        ┌─────────────────────┐
                                        │   internal/app      │
                                        │   (Core logic)      │
                                        └─────────────────────┘
```

- **Go→React**: Events via `runtime.EventsEmit()`
- **React→Go**: Method calls via auto-generated bindings
- **Thread safety**: `sync.RWMutex` for concurrent state access

## Ubuntu 24.04 Note

Ubuntu 24.04 uses `webkit2gtk-4.1` instead of `4.0`. Use the `-tags webkit2_41` build flag:

```bash
wails build -tags webkit2_41
wails dev -tags webkit2_41
```

The Makefile includes this automatically.

## License

MIT License - OpenMined
