// Email validation - safe regex pattern to avoid ReDoS
export const validateEmail = (email: string): string | null => {
  if (!email) return 'Email is required';

  // Simplified regex to avoid ReDoS vulnerability
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

  if (!emailRegex.test(email) || email.length >= 255) {
    return 'Please enter a valid email address';
  }

  return null;
};

// Password validation with strength checking
export const validatePassword = (password: string): string | null => {
  if (!password) return 'Password is required';
  if (password.length < 6) return 'Password must be at least 6 characters';
  return null;
};

// Password strength checker
export const getPasswordStrength = (password: string): number => {
  let strength = 0;
  if (password.length >= 8) strength++;
  if (password.length >= 12) strength++;

  // Use simpler checks to avoid ReDoS
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++;
  if (/\d/.test(password)) strength++;
  if (/[^a-zA-Z0-9]/.test(password)) strength++;

  return strength;
};

// Name validation
export const validateName = (name: string): string | null => {
  if (!name) return 'Name is required';
  if (name.length < 2) return 'Name must be at least 2 characters';
  if (name.length > 50) return 'Name must be less than 50 characters';
  return null;
};

// Confirm password validation
export const validateConfirmPassword = (
  password: string,
  confirmPassword: string
): string | null => {
  if (!confirmPassword) return 'Please confirm your password';
  if (password !== confirmPassword) return 'Passwords do not match';
  return null;
};

// ============================================================================
// Endpoint Path Validation
// ============================================================================

export interface EndpointPathValidationResult {
  isValid: boolean;
  error?: string;
  normalizedPath?: string;
}

/**
 * Validates an endpoint path in the format "owner/slug".
 *
 * Rules:
 * - Owner: starts with letter, alphanumeric + hyphens/underscores, 1-39 chars
 * - Slug: alphanumeric + hyphens/underscores, 1-100 chars
 * - Total path max 140 chars
 */
export const validateEndpointPath = (path: string): EndpointPathValidationResult => {
  const trimmed = path.trim();

  // Check empty
  if (!trimmed) {
    return { isValid: false, error: 'Path cannot be empty' };
  }

  // Check for slash
  if (!trimmed.includes('/')) {
    return {
      isValid: false,
      error: 'Invalid format. Use owner/endpoint-name (e.g., john/my-dataset)'
    };
  }

  // Split into owner and slug
  const parts = trimmed.split('/');
  if (parts.length !== 2) {
    return {
      isValid: false,
      error: 'Path must have exactly one slash: owner/endpoint-name'
    };
  }

  const [owner, slug] = parts;

  // Validate owner
  if (!owner || owner.length === 0) {
    return { isValid: false, error: 'Owner name is required' };
  }
  if (owner.length > 39) {
    return { isValid: false, error: 'Owner name must be 39 characters or less' };
  }
  if (!/^[a-zA-Z][\w-]*$/.test(owner)) {
    return {
      isValid: false,
      error:
        'Owner must start with a letter and contain only letters, numbers, hyphens, or underscores'
    };
  }

  // Validate slug
  if (!slug || slug.length === 0) {
    return { isValid: false, error: 'Endpoint name is required' };
  }
  if (slug.length > 100) {
    return { isValid: false, error: 'Endpoint name must be 100 characters or less' };
  }
  if (!/^[\w-]+$/.test(slug)) {
    return {
      isValid: false,
      error: 'Endpoint name can only contain letters, numbers, hyphens, or underscores'
    };
  }

  // Return normalized path (lowercase)
  return {
    isValid: true,
    normalizedPath: trimmed.toLowerCase()
  };
};

/**
 * Checks if an endpoint path is a duplicate of existing sources.
 */
export const isDuplicateEndpointPath = (
  path: string,
  existingCustomSources: string[],
  selectedSourcePaths: string[]
): boolean => {
  const normalized = path.toLowerCase().trim();

  // Check against custom sources
  if (existingCustomSources.some((s) => s.toLowerCase() === normalized)) {
    return true;
  }

  // Check against selected sources
  if (selectedSourcePaths.some((p) => p.toLowerCase() === normalized)) {
    return true;
  }

  return false;
};

/**
 * Filters available sources based on a search query for autocomplete.
 * Matches against full_path, name, and slug.
 */
export const filterSourcesForAutocomplete = <
  T extends { full_path?: string; name: string; slug: string }
>(
  sources: T[],
  query: string,
  maxResults = 5
): T[] => {
  const trimmed = query.trim().toLowerCase();

  if (!trimmed) {
    return [];
  }

  return sources
    .filter(
      (source) =>
        (source.full_path?.toLowerCase().includes(trimmed) ?? false) ||
        source.name.toLowerCase().includes(trimmed) ||
        source.slug.toLowerCase().includes(trimmed)
    )
    .slice(0, maxResults);
};
