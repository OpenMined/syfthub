package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

const schema = `
CREATE TABLE IF NOT EXISTS packages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('model', 'data_source', 'agent')),
    author      TEXT NOT NULL,
    version     TEXT NOT NULL,
    tags_json   TEXT NOT NULL DEFAULT '[]',
    config_json TEXT NOT NULL DEFAULT '[]',
    zip_data    BLOB,
    zip_sha256  TEXT NOT NULL DEFAULT '',
    zip_size    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
`

// Store is the SQLite-backed package repository.
type Store struct {
	db *sql.DB
}

// NewStore opens (or creates) the SQLite database and applies the schema.
func NewStore(dbPath string) (*Store, error) {
	db, err := sql.Open("sqlite3", dbPath+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, fmt.Errorf("apply schema: %w", err)
	}
	if err := migrateDB(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("migrate database: %w", err)
	}
	return &Store{db: db}, nil
}

// migrateDB applies incremental schema migrations to an existing database.
// SQLite does not support ALTER TABLE ... MODIFY CONSTRAINT, so to widen the
// type CHECK we recreate the table preserving all existing rows.
func migrateDB(db *sql.DB) error {
	// Check whether the packages table already allows 'agent'. We do this by
	// inspecting the CREATE TABLE statement stored in sqlite_master.
	var ddl string
	row := db.QueryRow(`SELECT sql FROM sqlite_master WHERE type='table' AND name='packages'`)
	if err := row.Scan(&ddl); err != nil {
		return nil // Table doesn't exist yet; nothing to migrate.
	}

	// If the DDL already includes 'agent' in the CHECK constraint, we're done.
	if containsAgentCheck(ddl) {
		return nil
	}

	// Recreate the table with the updated CHECK constraint, preserving data.
	// Each statement must be a separate Exec call — the Go SQLite driver only
	// executes the first statement in a multi-statement string.
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("begin migration: %w", err)
	}
	defer tx.Rollback() //nolint:errcheck

	if _, err := tx.Exec(`ALTER TABLE packages RENAME TO packages_old`); err != nil {
		return fmt.Errorf("rename table: %w", err)
	}
	if _, err := tx.Exec(schema); err != nil {
		return fmt.Errorf("create new table: %w", err)
	}
	if _, err := tx.Exec(`INSERT INTO packages (id, slug, name, description, type, author, version, tags_json, config_json, zip_data, zip_sha256, zip_size, created_at, updated_at)
		SELECT id, slug, name, description, type, author, version, tags_json, config_json, zip_data, zip_sha256, zip_size, created_at, updated_at FROM packages_old`); err != nil {
		return fmt.Errorf("copy data: %w", err)
	}
	if _, err := tx.Exec(`DROP TABLE packages_old`); err != nil {
		return fmt.Errorf("drop old table: %w", err)
	}
	return tx.Commit()
}

// containsAgentCheck reports whether a CREATE TABLE DDL string already
// contains 'agent' as a valid type in the CHECK constraint.
func containsAgentCheck(ddl string) bool {
	return strings.Contains(ddl, "'agent'") || strings.Contains(ddl, `"agent"`)
}

// Close closes the database connection.
func (s *Store) Close() error {
	return s.db.Close()
}

// scanPackage scans a row into a Package struct.
func scanPackage(row interface{ Scan(...any) error }) (*Package, error) {
	var p Package
	var tagsJSON, configJSON string
	var createdAt, updatedAt string

	err := row.Scan(
		&p.ID, &p.Slug, &p.Name, &p.Description, &p.Type,
		&p.Author, &p.Version, &tagsJSON, &configJSON,
		&p.ZipSHA256, &p.ZipSize,
		&createdAt, &updatedAt,
	)
	if err != nil {
		return nil, err
	}

	if err := json.Unmarshal([]byte(tagsJSON), &p.Tags); err != nil {
		p.Tags = []string{}
	}
	if p.Tags == nil {
		p.Tags = []string{}
	}

	if err := json.Unmarshal([]byte(configJSON), &p.Config); err != nil {
		p.Config = []PackageConfigField{}
	}
	if p.Config == nil {
		p.Config = []PackageConfigField{}
	}

	p.CreatedAt, _ = time.Parse(time.RFC3339, createdAt)
	p.UpdatedAt, _ = time.Parse(time.RFC3339, updatedAt)

	return &p, nil
}

const selectColumns = `id, slug, name, description, type, author, version, tags_json, config_json, zip_sha256, zip_size, created_at, updated_at`

// List returns packages matching the given options, plus the total count.
func (s *Store) List(ctx context.Context, opts ListOptions) ([]Package, int, error) {
	where := "1=1"
	args := []any{}

	if opts.Type != "" {
		where += " AND type = ?"
		args = append(args, opts.Type)
	}
	if opts.Tag != "" {
		where += " AND tags_json LIKE ?"
		args = append(args, "%"+opts.Tag+"%")
	}
	if opts.Query != "" {
		like := "%" + opts.Query + "%"
		where += " AND (name LIKE ? OR description LIKE ?)"
		args = append(args, like, like)
	}

	// Get total count
	var total int
	countQuery := "SELECT COUNT(*) FROM packages WHERE " + where
	if err := s.db.QueryRowContext(ctx, countQuery, args...).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("count packages: %w", err)
	}

	// Get page
	limit := opts.Limit
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	offset := opts.Offset
	if offset < 0 {
		offset = 0
	}

	query := fmt.Sprintf("SELECT %s FROM packages WHERE %s ORDER BY id ASC LIMIT ? OFFSET ?", selectColumns, where)
	pageArgs := append(args, limit, offset)
	rows, err := s.db.QueryContext(ctx, query, pageArgs...)
	if err != nil {
		return nil, 0, fmt.Errorf("list packages: %w", err)
	}
	defer rows.Close()

	packages := []Package{}
	for rows.Next() {
		p, err := scanPackage(rows)
		if err != nil {
			return nil, 0, fmt.Errorf("scan package: %w", err)
		}
		packages = append(packages, *p)
	}
	return packages, total, rows.Err()
}

// Get returns a single package by slug.
func (s *Store) Get(ctx context.Context, slug string) (*Package, error) {
	query := fmt.Sprintf("SELECT %s FROM packages WHERE slug = ?", selectColumns)
	row := s.db.QueryRowContext(ctx, query, slug)
	p, err := scanPackage(row)
	if err == sql.ErrNoRows {
		return nil, &NotFoundError{Slug: slug}
	}
	if err != nil {
		return nil, fmt.Errorf("get package: %w", err)
	}
	return p, nil
}

// Create inserts a new package.
func (s *Store) Create(ctx context.Context, pkg *Package) error {
	tagsJSON, _ := json.Marshal(pkg.Tags)
	configJSON, _ := json.Marshal(pkg.Config)
	now := time.Now().UTC().Format(time.RFC3339)

	result, err := s.db.ExecContext(ctx,
		`INSERT INTO packages (slug, name, description, type, author, version, tags_json, config_json, zip_data, zip_sha256, zip_size, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		pkg.Slug, pkg.Name, pkg.Description, pkg.Type, pkg.Author, pkg.Version,
		string(tagsJSON), string(configJSON), nil, pkg.ZipSHA256, pkg.ZipSize,
		now, now,
	)
	if err != nil {
		// SQLite UNIQUE constraint violation
		if isUniqueViolation(err) {
			return &ConflictError{Slug: pkg.Slug}
		}
		return fmt.Errorf("create package: %w", err)
	}

	id, _ := result.LastInsertId()
	pkg.ID = id
	pkg.CreatedAt, _ = time.Parse(time.RFC3339, now)
	pkg.UpdatedAt = pkg.CreatedAt
	return nil
}

// Update applies a merge-patch to an existing package.
func (s *Store) Update(ctx context.Context, slug string, req *UpdatePackageRequest) (*Package, error) {
	pkg, err := s.Get(ctx, slug)
	if err != nil {
		return nil, err
	}

	if req.Name != nil {
		pkg.Name = *req.Name
	}
	if req.Description != nil {
		pkg.Description = *req.Description
	}
	if req.Type != nil {
		pkg.Type = *req.Type
	}
	if req.Author != nil {
		pkg.Author = *req.Author
	}
	if req.Version != nil {
		pkg.Version = *req.Version
	}
	if req.Tags != nil {
		pkg.Tags = *req.Tags
	}
	if req.Config != nil {
		pkg.Config = *req.Config
	}

	tagsJSON, _ := json.Marshal(pkg.Tags)
	configJSON, _ := json.Marshal(pkg.Config)
	now := time.Now().UTC().Format(time.RFC3339)

	_, err = s.db.ExecContext(ctx,
		`UPDATE packages SET name=?, description=?, type=?, author=?, version=?, tags_json=?, config_json=?, updated_at=? WHERE slug=?`,
		pkg.Name, pkg.Description, pkg.Type, pkg.Author, pkg.Version,
		string(tagsJSON), string(configJSON), now, slug,
	)
	if err != nil {
		return nil, fmt.Errorf("update package: %w", err)
	}

	pkg.UpdatedAt, _ = time.Parse(time.RFC3339, now)
	return pkg, nil
}

// Delete removes a package by slug.
func (s *Store) Delete(ctx context.Context, slug string) error {
	result, err := s.db.ExecContext(ctx, "DELETE FROM packages WHERE slug = ?", slug)
	if err != nil {
		return fmt.Errorf("delete package: %w", err)
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return &NotFoundError{Slug: slug}
	}
	return nil
}

// GetZip returns the zip data and sha256 for a package.
func (s *Store) GetZip(ctx context.Context, slug string) ([]byte, string, error) {
	var data []byte
	var sha256 string
	err := s.db.QueryRowContext(ctx, "SELECT zip_data, zip_sha256 FROM packages WHERE slug = ?", slug).Scan(&data, &sha256)
	if err == sql.ErrNoRows {
		return nil, "", &NotFoundError{Slug: slug}
	}
	if err != nil {
		return nil, "", fmt.Errorf("get zip: %w", err)
	}
	if data == nil {
		return nil, "", &NotFoundError{Slug: slug}
	}
	return data, sha256, nil
}

// SetZip stores the zip data and sha256 for a package.
func (s *Store) SetZip(ctx context.Context, slug string, data []byte, sha256hex string) error {
	result, err := s.db.ExecContext(ctx,
		"UPDATE packages SET zip_data=?, zip_sha256=?, zip_size=?, updated_at=? WHERE slug=?",
		data, sha256hex, len(data), time.Now().UTC().Format(time.RFC3339), slug,
	)
	if err != nil {
		return fmt.Errorf("set zip: %w", err)
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return &NotFoundError{Slug: slug}
	}
	return nil
}

// Count returns the total number of packages.
func (s *Store) Count(ctx context.Context) (int, error) {
	var count int
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM packages").Scan(&count); err != nil {
		return 0, fmt.Errorf("count packages: %w", err)
	}
	return count, nil
}

// isUniqueViolation checks if the error is a SQLite UNIQUE constraint violation.
func isUniqueViolation(err error) bool {
	return err != nil && (strings.Contains(err.Error(), "UNIQUE constraint failed") || strings.Contains(err.Error(), "unique constraint"))
}
