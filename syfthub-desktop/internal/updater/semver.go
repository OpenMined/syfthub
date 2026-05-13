package updater

import (
	"strconv"
	"strings"
)

// Minimal SemVer 2.0 implementation, focused on what the updater needs:
// validate, compare, and detect pre-releases. No build-metadata handling
// beyond ignoring everything after "+". Inputs may omit the leading "v".
//
// This is deliberately not golang.org/x/mod/semver to avoid bumping the
// module's Go version requirement, which would break the CI Go 1.23 job.

type semver struct {
	major, minor, patch int
	prerelease          string // raw, e.g. "rc.1" (no leading "-")
	valid               bool
}

func parseSemver(s string) semver {
	s = strings.TrimPrefix(s, "v")
	if s == "" {
		return semver{}
	}
	// Strip build metadata.
	if i := strings.IndexByte(s, '+'); i >= 0 {
		s = s[:i]
	}
	core := s
	pre := ""
	if i := strings.IndexByte(s, '-'); i >= 0 {
		core = s[:i]
		pre = s[i+1:]
	}
	parts := strings.SplitN(core, ".", 3)
	if len(parts) != 3 {
		return semver{}
	}
	out := semver{prerelease: pre, valid: true}
	for i, p := range parts {
		if p == "" || (len(p) > 1 && p[0] == '0') {
			return semver{}
		}
		n, err := strconv.Atoi(p)
		if err != nil || n < 0 {
			return semver{}
		}
		switch i {
		case 0:
			out.major = n
		case 1:
			out.minor = n
		case 2:
			out.patch = n
		}
	}
	if pre != "" && !validPrerelease(pre) {
		return semver{}
	}
	return out
}

func validPrerelease(p string) bool {
	if p == "" {
		return false
	}
	for _, ident := range strings.Split(p, ".") {
		if ident == "" {
			return false
		}
		numeric := true
		for _, r := range ident {
			ok := (r >= '0' && r <= '9') || (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || r == '-'
			if !ok {
				return false
			}
			if !(r >= '0' && r <= '9') {
				numeric = false
			}
		}
		if numeric && len(ident) > 1 && ident[0] == '0' {
			return false
		}
	}
	return true
}

func comparePrerelease(a, b string) int {
	switch {
	case a == "" && b == "":
		return 0
	case a == "":
		return +1 // no prerelease > prerelease
	case b == "":
		return -1
	}
	aParts := strings.Split(a, ".")
	bParts := strings.Split(b, ".")
	n := len(aParts)
	if len(bParts) < n {
		n = len(bParts)
	}
	for i := 0; i < n; i++ {
		c := compareIdent(aParts[i], bParts[i])
		if c != 0 {
			return c
		}
	}
	switch {
	case len(aParts) < len(bParts):
		return -1
	case len(aParts) > len(bParts):
		return +1
	}
	return 0
}

func compareIdent(a, b string) int {
	an, aErr := strconv.Atoi(a)
	bn, bErr := strconv.Atoi(b)
	switch {
	case aErr == nil && bErr == nil:
		switch {
		case an < bn:
			return -1
		case an > bn:
			return +1
		}
		return 0
	case aErr == nil:
		return -1 // numeric < alphanumeric
	case bErr == nil:
		return +1
	}
	return strings.Compare(a, b)
}

// IsValidSemver reports whether s parses as semver. The leading "v" is
// optional — manifests carry bare versions like "0.2.0".
func IsValidSemver(s string) bool {
	return parseSemver(s).valid
}

// IsPreRelease reports whether s is a pre-release version.
func IsPreRelease(s string) bool {
	v := parseSemver(s)
	return v.valid && v.prerelease != ""
}

// CompareSemver returns -1, 0, +1 like strings.Compare. Pre-releases
// order below their base release. Invalid versions are treated as
// "newer than everything" so dev builds never get a stale
// "update available" prompt.
func CompareSemver(a, b string) int {
	va := parseSemver(a)
	vb := parseSemver(b)
	switch {
	case !va.valid && !vb.valid:
		return 0
	case !va.valid:
		return +1
	case !vb.valid:
		return -1
	}
	switch {
	case va.major < vb.major:
		return -1
	case va.major > vb.major:
		return +1
	case va.minor < vb.minor:
		return -1
	case va.minor > vb.minor:
		return +1
	case va.patch < vb.patch:
		return -1
	case va.patch > vb.patch:
		return +1
	}
	return comparePrerelease(va.prerelease, vb.prerelease)
}

// IsDevVersion reports whether s should be treated as a development
// build for the purpose of disabling the auto-updater. Any non-semver
// string, any pre-release, and the literal "dev" qualify.
func IsDevVersion(s string) bool {
	if s == "" || s == "dev" {
		return true
	}
	v := parseSemver(s)
	if !v.valid {
		return true
	}
	return v.prerelease != ""
}
