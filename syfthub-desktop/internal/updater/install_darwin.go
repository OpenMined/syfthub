//go:build darwin

package updater

import "os/exec"

// inPlaceSupported is false on macOS until code signing + notarization
// land. The frontend falls back to the Phase 2 manual install flow
// (download + reveal in Finder) when this returns false.
//
// To enable in-place install on macOS (Phase 4):
//
//  1. The release workflow must sign and notarize the .app bundle —
//     the scaffolding for this lives in release-desktop.yml under
//     `build-macos-arm64` and activates automatically when the
//     APPLE_DEVELOPER_ID_* and APPLE_NOTARIZATION_* secrets are set.
//
//  2. Flip inPlaceSupported to return true.
//
//  3. Implement swapAndRelaunch below using one of:
//
//       a. Sparkle (recommended for macOS). Embed via Wails's
//          Mac-platform NSWindow controller; let Sparkle own the
//          .app-bundle replace + relaunch dance. Sparkle's EdDSA
//          signature verification is independent of Apple notarization
//          and provides an additional integrity check.
//
//       b. Pure-Go ditto-based swap:
//             - The downloaded artifact is a .zip; unzip to a tmp dir.
//             - Resolve the parent .app from os.Executable() (walks up
//               until it finds <name>.app/Contents/MacOS/<binary>).
//             - rsync -a $tmp/X.app/ $appPath/ (atomic update of
//               bundle contents while preserving signature).
//             - xattr -dr com.apple.quarantine $appPath (only needed
//               for unsigned bundles; signed+notarized bundles don't
//               require this).
//             - exec the bundle: open -n $appPath.
//
// The pure-Go path is simpler operationally but loses Sparkle's
// signature-on-the-update step. Either way, Phase 5's manifest signing
// gives us cryptographic trust on the download itself, so the marginal
// security gain from Sparkle is bounded.

func inPlaceSupported() bool { return false }

func swapAndRelaunch(exePath, newBinaryPath string) error {
	return ErrUnsupportedPlatform
}

func startDetached(cmd *exec.Cmd) error {
	return cmd.Start()
}
