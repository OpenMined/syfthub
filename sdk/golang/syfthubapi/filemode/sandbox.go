// Package filemode — sandbox.go builds the synthetic code directory that
// every container mount exposes to runner.py. The synth dir contains ONLY
// code + explicitly declared resources; .env, policies, setup files, and
// any other ambient secrets are absent by construction.
//
// The synth dir is the host-side half of the container security boundary.
// At runtime the container bind-mounts it read-only at /app/synth and a
// further bwrap re-binds it at /app/code for the handler subprocess.
package filemode

import (
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
)

// SandboxManifest describes the classified view of an endpoint directory
// used to materialize a synth dir. It is computed from a LoadedEndpoint by
// BuildSandboxManifest and consumed by MaterializeSandbox.
type SandboxManifest struct {
	// EndpointDir is the absolute path of the endpoint on the host.
	EndpointDir string

	// CodePaths lists endpoint-relative *.py files that are exposed
	// read-only. Always includes runner.py.
	CodePaths []string

	// ResourcePaths lists endpoint-relative paths (files or directories)
	// that the developer explicitly exposed via sandbox.expose_resources.
	// Subdirs are copied recursively; files copied as-is.
	ResourcePaths []string

	// IncludePyProject mirrors the legacy "pyproject.toml at endpoint
	// root is part of the code surface" rule.
	IncludePyProject bool

	// WorkspaceSubPath is the endpoint-relative subdir that becomes the
	// per-invocation writable workspace (default: "workspace").
	WorkspaceSubPath string
}

// BuildSandboxManifest walks the endpoint dir and produces a classification
// suitable for MaterializeSandbox. It does NOT touch policy/.env/setup
// files — those are excluded by design.
func BuildSandboxManifest(le *LoadedEndpoint) (*SandboxManifest, error) {
	if le == nil || le.Dir == "" {
		return nil, fmt.Errorf("sandbox: nil endpoint or empty dir")
	}
	absRoot, err := filepath.Abs(le.Dir)
	if err != nil {
		return nil, fmt.Errorf("sandbox: resolve endpoint dir: %w", err)
	}

	m := &SandboxManifest{EndpointDir: absRoot}

	// 1. Code files: every *.py under the endpoint dir, except in well-known
	//    excluded subtrees and except secret files (none of which are .py).
	if err := filepath.Walk(absRoot, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, _ := filepath.Rel(absRoot, path)
		if isExcludedSubtree(rel) {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if info.IsDir() {
			return nil
		}
		if isSecretFile(rel) {
			return nil
		}
		if filepath.Ext(info.Name()) == ".py" {
			m.CodePaths = append(m.CodePaths, rel)
		}
		return nil
	}); err != nil {
		return nil, fmt.Errorf("sandbox: walk endpoint dir: %w", err)
	}

	// 2. pyproject.toml at root, if present.
	if _, err := os.Stat(filepath.Join(absRoot, "pyproject.toml")); err == nil {
		m.IncludePyProject = true
	}

	// 3. Declared resources from frontmatter (cleaned, normalized).
	for _, raw := range le.Config.Sandbox.ExposeResources {
		clean := filepath.Clean(strings.TrimSpace(raw))
		if clean == "" || clean == "." || clean == ".." {
			continue
		}
		if filepath.IsAbs(clean) {
			return nil, fmt.Errorf("sandbox: expose_resources entry %q must be relative", raw)
		}
		if strings.HasPrefix(clean, "..") {
			return nil, fmt.Errorf("sandbox: expose_resources entry %q must stay inside endpoint dir", raw)
		}
		if isSecretFile(clean) || isExcludedSubtree(clean) {
			return nil, fmt.Errorf("sandbox: expose_resources entry %q overlaps a reserved path", raw)
		}
		m.ResourcePaths = append(m.ResourcePaths, clean)
	}

	// 4. Workspace path (default: "workspace").
	if ws := le.Config.Sandbox.Workspace.Path; ws != "" {
		clean := filepath.Clean(strings.TrimSpace(ws))
		if filepath.IsAbs(clean) || strings.HasPrefix(clean, "..") {
			return nil, fmt.Errorf("sandbox: workspace path %q must be relative and stay inside endpoint dir", ws)
		}
		m.WorkspaceSubPath = clean
	} else {
		m.WorkspaceSubPath = "workspace"
	}

	return m, nil
}

// MaterializeSandbox builds the synth dir at dest from m. dest is created
// fresh; it is the caller's responsibility to remove it when done.
//
// Files are hardlinked when on the same filesystem (zero-copy) and copied
// otherwise. Symlinks are resolved to their real targets and rejected if
// they point outside the endpoint dir — this is the defense against an
// "innocent" symlink that escapes the endpoint sandbox tree.
//
// The dest tree is laid out as:
//
//	dest/                        chmod 0755
//	├── runner.py                (read-only; hardlink or copy)
//	├── pyproject.toml           (if present)
//	├── <other *.py>             (preserved relative paths)
//	└── <exposed resources>      (recursive)
//
// .env, policy/, setup.yaml, .setup-state.json are NEVER included.
func MaterializeSandbox(m *SandboxManifest, dest string, logger *slog.Logger) error {
	if m == nil {
		return fmt.Errorf("sandbox: nil manifest")
	}
	if logger == nil {
		logger = slog.Default()
	}

	if err := os.MkdirAll(dest, 0o755); err != nil {
		return fmt.Errorf("sandbox: create dest: %w", err)
	}

	// Copy code files (preserving relative paths).
	for _, rel := range m.CodePaths {
		if err := materializePath(m.EndpointDir, rel, dest, false); err != nil {
			return fmt.Errorf("sandbox: code %q: %w", rel, err)
		}
	}

	if m.IncludePyProject {
		if err := materializePath(m.EndpointDir, "pyproject.toml", dest, false); err != nil {
			return fmt.Errorf("sandbox: pyproject.toml: %w", err)
		}
	}

	// Copy declared resources (recursive for directories).
	for _, rel := range m.ResourcePaths {
		if err := materializePath(m.EndpointDir, rel, dest, true); err != nil {
			return fmt.Errorf("sandbox: resource %q: %w", rel, err)
		}
	}

	logger.Debug("sandbox materialized",
		"src", m.EndpointDir,
		"dest", dest,
		"code_files", len(m.CodePaths),
		"resources", len(m.ResourcePaths),
	)
	return nil
}

// materializePath copies src/rel to dest/rel. When recursive is true and
// the source is a directory, the subtree is copied. Symlinks are resolved;
// targets that escape src are rejected.
func materializePath(src, rel, dest string, recursive bool) error {
	srcPath := filepath.Join(src, rel)
	destPath := filepath.Join(dest, rel)

	info, err := os.Lstat(srcPath)
	if err != nil {
		return err
	}

	// Fast path: non-symlink. Use the Lstat info directly and skip
	// EvalSymlinks (a syscall chain per path segment).
	real := srcPath
	realInfo := info
	if info.Mode()&os.ModeSymlink != 0 {
		resolved, evalErr := filepath.EvalSymlinks(srcPath)
		if evalErr != nil {
			// Broken link: treat as missing (skip silently for non-code resources).
			if errors.Is(evalErr, os.ErrNotExist) {
				return nil
			}
			return fmt.Errorf("resolve %q: %w", rel, evalErr)
		}
		absSrc, _ := filepath.Abs(src)
		if !pathIsUnder(resolved, absSrc) {
			return fmt.Errorf("symlink escape: %q resolves to %q (outside %q)", rel, resolved, absSrc)
		}
		real = resolved
		realInfo, err = os.Stat(resolved)
		if err != nil {
			return err
		}
	}

	if realInfo.IsDir() {
		if !recursive {
			return fmt.Errorf("expected file at %q, got directory", rel)
		}
		absSrc, _ := filepath.Abs(src)
		return copyTreeWithRoot(real, destPath, absSrc)
	}

	if err := os.MkdirAll(filepath.Dir(destPath), 0o755); err != nil {
		return err
	}
	return linkOrCopyFile(real, destPath, info.Mode())
}

// copyTreeWithRoot walks src and materializes every file under dest,
// rejecting symlinks that escape rootAbs (the endpoint dir).
func copyTreeWithRoot(src, dest, rootAbs string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, _ := filepath.Rel(src, path)
		target := filepath.Join(dest, rel)

		// Resolve symlink, reject escape.
		real, err := filepath.EvalSymlinks(path)
		if err != nil {
			if errors.Is(err, os.ErrNotExist) {
				return nil
			}
			return err
		}
		if !pathIsUnder(real, rootAbs) {
			return fmt.Errorf("symlink escape: %q -> %q", path, real)
		}

		realInfo, err := os.Stat(real)
		if err != nil {
			return err
		}
		if realInfo.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		return linkOrCopyFile(real, target, info.Mode())
	})
}

// linkOrCopyFile first tries os.Link (free on same filesystem). On EXDEV
// or other errors it falls back to a content copy. The destination is
// chmod'd to remove write bits — the synth dir is treated as read-only
// even before the container/bwrap mount makes it formally read-only.
func linkOrCopyFile(src, dest string, mode os.FileMode) error {
	if err := os.Link(src, dest); err == nil {
		return nil
	}
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, mode.Perm())
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	// Strip write bits — synth dir is read-only-by-policy.
	return os.Chmod(dest, mode.Perm()&^0o222)
}

// secretFileNames matches any path segment that MUST NEVER be exposed
// to the handler — checked at every depth so e.g. nested ".env" hits.
var secretFileNames = map[string]struct{}{
	".env":              {},
	"setup.yaml":        {},
	".setup-state.json": {},
	"policies.yaml":     {},
	"policy":            {}, // directory: matches whole subtree below
}

// isSecretFile reports whether rel (an endpoint-relative path) names a
// file or directory that MUST NEVER be exposed to the handler.
func isSecretFile(rel string) bool {
	clean := filepath.ToSlash(filepath.Clean(rel))
	for _, seg := range strings.Split(clean, "/") {
		if _, ok := secretFileNames[seg]; ok {
			return true
		}
	}
	return false
}

// isExcludedSubtree reports whether rel sits inside a directory we never
// scan for code (caches, venvs, hidden dirs). Mirrors loader-level
// exclusions used by LoadAll.
func isExcludedSubtree(rel string) bool {
	clean := filepath.ToSlash(filepath.Clean(rel))
	if clean == "." {
		return false
	}
	for _, seg := range strings.Split(clean, "/") {
		switch seg {
		case "__pycache__",
			".venv",
			"venv",
			"node_modules",
			".git",
			".mypy_cache",
			".pytest_cache",
			"workspace": // workspace is bound separately, not via synth dir
			return true
		}
		if strings.HasPrefix(seg, ".") && seg != "." && seg != ".." {
			// Hidden dirs and files (covers .env, .DS_Store, etc.)
			return true
		}
	}
	return false
}
