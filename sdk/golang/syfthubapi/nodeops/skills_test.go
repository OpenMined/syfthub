package nodeops

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestValidateSkillName(t *testing.T) {
	good := []string{"a", "abc", "abc-123", "abc_123", "0skill", "foo-bar-baz"}
	for _, n := range good {
		if err := ValidateSkillName(n); err != nil {
			t.Errorf("ValidateSkillName(%q) = %v, want nil", n, err)
		}
	}
	bad := []string{
		"", "Foo", "ABC", "-foo", "_foo", "foo bar", "foo/bar",
		"foo..bar", "foo.bar", "../escape", "f" + repeat("o", 100),
	}
	for _, n := range bad {
		if err := ValidateSkillName(n); err == nil {
			t.Errorf("ValidateSkillName(%q) = nil, want error", n)
		}
	}
}

func TestListSkills_Empty(t *testing.T) {
	dir := t.TempDir()
	skills, err := ListSkills(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(skills) != 0 {
		t.Errorf("expected 0 skills, got %d", len(skills))
	}
}

func TestWriteAndListSkills(t *testing.T) {
	dir := t.TempDir()

	if err := WriteSkill(dir, "alpha", "# Alpha skill\nDo the alpha thing.\n"); err != nil {
		t.Fatal(err)
	}
	if err := WriteSkill(dir, "beta", "# Beta\nDo beta.\n"); err != nil {
		t.Fatal(err)
	}

	// Verify on-disk layout.
	want := filepath.Join(dir, "skills", "alpha", "SKILL.md")
	if _, err := os.Stat(want); err != nil {
		t.Fatalf("expected %s to exist: %v", want, err)
	}

	skills, err := ListSkills(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(skills) != 2 {
		t.Fatalf("expected 2 skills, got %d", len(skills))
	}
	if skills[0].Name != "alpha" || skills[1].Name != "beta" {
		t.Errorf("skill order = [%s, %s], want [alpha, beta]", skills[0].Name, skills[1].Name)
	}
	if skills[0].Title != "Alpha skill" {
		t.Errorf("alpha title = %q, want %q", skills[0].Title, "Alpha skill")
	}
	if skills[0].Size == 0 {
		t.Error("alpha size = 0")
	}
}

func TestWriteSkill_RejectsBadName(t *testing.T) {
	dir := t.TempDir()
	if err := WriteSkill(dir, "../escape", "body"); err == nil {
		t.Error("expected error for path-traversal name")
	}
	if err := WriteSkill(dir, "Foo", "body"); err == nil {
		t.Error("expected error for uppercase name")
	}
	if err := WriteSkill(dir, "ok", "   \n\t  "); err == nil {
		t.Error("expected error for empty body")
	}
}

func TestWriteSkill_RequiresEndpointDir(t *testing.T) {
	if err := WriteSkill("/nonexistent/path/xyz123", "foo", "body"); err == nil {
		t.Error("expected error when endpoint dir does not exist")
	}
}

func TestWriteSkill_TouchesEnv(t *testing.T) {
	dir := t.TempDir()
	envPath := filepath.Join(dir, ".env")
	if err := os.WriteFile(envPath, []byte("FOO=bar\n"), 0600); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-1 * time.Hour)
	if err := os.Chtimes(envPath, old, old); err != nil {
		t.Fatal(err)
	}

	if err := WriteSkill(dir, "foo", "# Foo"); err != nil {
		t.Fatal(err)
	}

	st, err := os.Stat(envPath)
	if err != nil {
		t.Fatal(err)
	}
	if !st.ModTime().After(old.Add(30 * time.Minute)) {
		t.Errorf(".env mtime not updated: got %v", st.ModTime())
	}
}

func TestWriteSkill_CreatesEnvIfMissing(t *testing.T) {
	dir := t.TempDir()
	if err := WriteSkill(dir, "foo", "# Foo"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, ".env")); err != nil {
		t.Errorf("expected .env to be created, got %v", err)
	}
}

func TestReadSkill(t *testing.T) {
	dir := t.TempDir()
	body := "# Title\n\nBody line.\n"
	if err := WriteSkill(dir, "x", body); err != nil {
		t.Fatal(err)
	}
	got, err := ReadSkill(dir, "x")
	if err != nil {
		t.Fatal(err)
	}
	if got != body {
		t.Errorf("ReadSkill = %q, want %q", got, body)
	}
}

func TestReadSkill_Missing(t *testing.T) {
	dir := t.TempDir()
	_, err := ReadSkill(dir, "missing")
	if err == nil || !os.IsNotExist(err) {
		t.Errorf("expected os.IsNotExist, got %v", err)
	}
}

func TestRemoveSkill(t *testing.T) {
	dir := t.TempDir()
	if err := WriteSkill(dir, "rmme", "# rmme"); err != nil {
		t.Fatal(err)
	}
	if err := RemoveSkill(dir, "rmme"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, "skills", "rmme")); !os.IsNotExist(err) {
		t.Errorf("expected skill dir removed, got err=%v", err)
	}
}

func TestRemoveSkill_Missing(t *testing.T) {
	dir := t.TempDir()
	err := RemoveSkill(dir, "ghost")
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, os.ErrNotExist) {
		t.Errorf("err = %v, want os.ErrNotExist", err)
	}
}

func TestListSkills_SkipsBadEntries(t *testing.T) {
	dir := t.TempDir()
	skillsDir := filepath.Join(dir, "skills")
	if err := os.MkdirAll(filepath.Join(skillsDir, "Bad-Name"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(skillsDir, "Bad-Name", "SKILL.md"), []byte("x"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(skillsDir, "loose-file.md"), []byte("x"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(skillsDir, "no-skillmd"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := WriteSkill(dir, "good", "# good"); err != nil {
		t.Fatal(err)
	}

	skills, err := ListSkills(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(skills) != 1 || skills[0].Name != "good" {
		t.Errorf("got %v, want exactly [good]", skillNames(skills))
	}
}

func skillNames(s []SkillInfo) []string {
	names := make([]string, len(s))
	for i, x := range s {
		names[i] = x.Name
	}
	return names
}

func repeat(s string, n int) string {
	return strings.Repeat(s, n)
}
