package nodeops

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// SkillsDirName is the conventional subdirectory under an endpoint that holds
// skill bundles. Each skill is a directory containing a SKILL.md file, matching
// the layout the agent runners (claude-agent, research-agent) expect.
const SkillsDirName = "skills"

// SkillFileName is the canonical filename inside each skill directory. The
// runner-side loader matches case-insensitively, but we always write upper-S.
const SkillFileName = "SKILL.md"

var skillNameRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,63}$`)

// SkillInfo describes a skill bundle on disk.
type SkillInfo struct {
	Name       string    // subdirectory name
	Path       string    // absolute path to SKILL.md
	Title      string    // first markdown heading or Name
	Size       int64     // size of SKILL.md
	ModifiedAt time.Time // mtime of SKILL.md
}

// ValidateSkillName returns an error if name is unsuitable as a skill directory.
// Names must match ^[a-z0-9][a-z0-9_-]{0,63}$.
func ValidateSkillName(name string) error {
	if name == "" {
		return fmt.Errorf("skill name is required")
	}
	if !skillNameRe.MatchString(name) {
		return fmt.Errorf("invalid skill name %q: must match ^[a-z0-9][a-z0-9_-]{0,63}$", name)
	}
	return nil
}

// ListSkills returns every <endpointDir>/skills/<name>/SKILL.md, sorted by name.
// Returns an empty slice (not nil) if the skills directory is missing or empty.
func ListSkills(endpointDir string) ([]SkillInfo, error) {
	if endpointDir == "" {
		return nil, fmt.Errorf("endpoint directory is required")
	}
	skillsDir := filepath.Join(endpointDir, SkillsDirName)
	entries, err := os.ReadDir(skillsDir)
	if err != nil {
		if os.IsNotExist(err) {
			return []SkillInfo{}, nil
		}
		return nil, fmt.Errorf("read skills dir: %w", err)
	}

	skills := make([]SkillInfo, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		name := e.Name()
		if err := ValidateSkillName(name); err != nil {
			// Silently skip directories that don't match the convention.
			continue
		}
		skillPath := filepath.Join(skillsDir, name, SkillFileName)
		st, err := os.Stat(skillPath)
		if err != nil {
			continue
		}
		skills = append(skills, SkillInfo{
			Name:       name,
			Path:       skillPath,
			Title:      readSkillTitle(skillPath, name),
			Size:       st.Size(),
			ModifiedAt: st.ModTime(),
		})
	}
	sort.Slice(skills, func(i, j int) bool { return skills[i].Name < skills[j].Name })
	return skills, nil
}

// ReadSkill returns the body of <endpointDir>/skills/<name>/SKILL.md.
func ReadSkill(endpointDir, name string) (string, error) {
	if err := ValidateSkillName(name); err != nil {
		return "", err
	}
	path := filepath.Join(endpointDir, SkillsDirName, name, SkillFileName)
	body, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

// WriteSkill creates or overwrites <endpointDir>/skills/<name>/SKILL.md with
// body. The parent endpoint directory must already exist. After a successful
// write, .env mtime is touched to force the file watcher to fire a reload
// event even if it hasn't yet registered the new skill subdirectory.
func WriteSkill(endpointDir, name, body string) error {
	if err := ValidateSkillName(name); err != nil {
		return err
	}
	if strings.TrimSpace(body) == "" {
		return fmt.Errorf("skill body is empty")
	}
	if endpointDir == "" {
		return fmt.Errorf("endpoint directory is required")
	}
	if st, err := os.Stat(endpointDir); err != nil || !st.IsDir() {
		return fmt.Errorf("endpoint directory does not exist: %s", endpointDir)
	}

	skillDir := filepath.Join(endpointDir, SkillsDirName, name)
	if err := os.MkdirAll(skillDir, 0755); err != nil {
		return fmt.Errorf("create skill dir: %w", err)
	}
	skillPath := filepath.Join(skillDir, SkillFileName)
	if err := os.WriteFile(skillPath, []byte(body), 0644); err != nil {
		return fmt.Errorf("write %s: %w", SkillFileName, err)
	}
	touchEnv(endpointDir)
	return nil
}

// RemoveSkill deletes <endpointDir>/skills/<name>/ recursively and touches .env.
// Returns os.ErrNotExist if the skill does not exist.
func RemoveSkill(endpointDir, name string) error {
	if err := ValidateSkillName(name); err != nil {
		return err
	}
	if endpointDir == "" {
		return fmt.Errorf("endpoint directory is required")
	}
	skillDir := filepath.Join(endpointDir, SkillsDirName, name)
	if _, err := os.Stat(skillDir); err != nil {
		return err
	}
	if err := os.RemoveAll(skillDir); err != nil {
		return fmt.Errorf("remove skill dir: %w", err)
	}
	touchEnv(endpointDir)
	return nil
}

// touchEnv updates the mtime on <endpointDir>/.env so the fsnotify watcher
// fires a Write event on a path it already watches. Mirrors the trick used by
// setupflow/engine.go after setup completes. Best-effort; errors are ignored
// because the caller has already mutated the skills directory successfully.
func touchEnv(endpointDir string) {
	envPath := filepath.Join(endpointDir, ".env")
	if _, err := os.Stat(envPath); os.IsNotExist(err) {
		// Create an empty .env so future touches succeed and the watcher
		// has something to fire on.
		_ = os.WriteFile(envPath, []byte{}, 0600)
		return
	}
	now := time.Now()
	_ = os.Chtimes(envPath, now, now)
}

// readSkillTitle returns the first markdown heading from path, or fallback if
// no heading is found in the first ~4KB.
func readSkillTitle(path, fallback string) string {
	f, err := os.Open(path)
	if err != nil {
		return fallback
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 4096), 64*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "#") {
			return strings.TrimSpace(strings.TrimLeft(line, "#"))
		}
	}
	return fallback
}
