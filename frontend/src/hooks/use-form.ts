import { useCallback, useState } from 'react';

import type React from 'react';

/**
 * Validator function type - returns error message or null if valid
 */
type Validator<T, K extends keyof T> = (value: T[K], allValues: T) => string | null;

/**
 * Options for the useForm hook
 */
interface UseFormOptions<T extends object> {
  /** Initial form values */
  initialValues: T;
  /** Validation functions for each field */
  validators?: { [K in keyof T]?: Validator<T, K> };
  /** Submit handler - receives validated form values */
  onSubmit: (values: T) => Promise<void> | void;
  /** Whether to validate fields on change (default: false) */
  validateOnChange?: boolean;
  /** Whether to validate fields on blur (default: true) */
  validateOnBlur?: boolean;
}

/**
 * Return type for the useForm hook
 */
interface UseFormReturn<T extends object> {
  /** Current form values */
  values: T;
  /** Current form errors (field name -> error message) */
  errors: Partial<Record<keyof T, string>>;
  /** Fields that have been touched (focused and blurred) */
  touched: Partial<Record<keyof T, boolean>>;
  /** Whether the form is currently submitting */
  isSubmitting: boolean;
  /** Whether all fields pass validation */
  isValid: boolean;
  /** Change handler factory - returns handler for specific field */
  handleChange: (field: keyof T) => (e: React.ChangeEvent<HTMLInputElement>) => void;
  /** Blur handler factory - returns handler for specific field */
  handleBlur: (field: keyof T) => () => void;
  /** Form submit handler - validates and calls onSubmit if valid */
  handleSubmit: (e: React.FormEvent) => Promise<void>;
  /** Manually set a field value */
  setFieldValue: <K extends keyof T>(field: K, value: T[K]) => void;
  /** Manually set a field error */
  setFieldError: (field: keyof T, error: string | null) => void;
  /** Reset form to initial values and clear errors */
  resetForm: () => void;
  /** Validate a single field and return error message */
  validateField: (field: keyof T) => string | null;
  /** Validate all fields and update errors state - returns true if valid */
  validateForm: () => boolean;
}

/**
 * useForm - Custom hook for form state management with validation.
 *
 * Provides a simple, type-safe way to manage form state, validation,
 * and submission. Similar to Formik or React Hook Form but lighter.
 *
 * @example
 * ```tsx
 * const { values, errors, handleChange, handleSubmit, isSubmitting } = useForm({
 *   initialValues: { email: '', password: '' },
 *   validators: {
 *     email: (value) => !value ? 'Email is required' : null,
 *     password: (value) => value.length < 6 ? 'Password too short' : null,
 *   },
 *   onSubmit: async (values) => {
 *     await loginAPI(values);
 *   },
 * });
 *
 * return (
 *   <form onSubmit={handleSubmit}>
 *     <input value={values.email} onChange={handleChange('email')} />
 *     {errors.email && <span>{errors.email}</span>}
 *     <button disabled={isSubmitting}>Submit</button>
 *   </form>
 * );
 * ```
 */
export function useForm<T extends object>({
  initialValues,
  validators = {},
  onSubmit,
  validateOnChange = false,
  validateOnBlur = true
}: UseFormOptions<T>): UseFormReturn<T> {
  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<Partial<Record<keyof T, string>>>({});
  const [touched, setTouched] = useState<Partial<Record<keyof T, boolean>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * Validate a single field
   */
  const validateField = useCallback(
    (field: keyof T): string | null => {
      const validator = validators[field];
      if (!validator) return null;
      return validator(values[field], values);
    },
    [validators, values]
  );

  /**
   * Validate all fields and update errors state
   */
  const validateForm = useCallback((): boolean => {
    const newErrors: Partial<Record<keyof T, string>> = {};
    let isValid = true;

    for (const field of Object.keys(validators) as Array<keyof T>) {
      const error = validateField(field);
      if (error) {
        newErrors[field] = error;
        isValid = false;
      }
    }

    setErrors(newErrors);
    return isValid;
  }, [validators, validateField]);

  /**
   * Check if form is valid (no errors)
   */
  const isValid = Object.keys(errors).length === 0;

  /**
   * Handle input change
   */
  const handleChange = useCallback(
    (field: keyof T) => (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value as T[keyof T];

      setValues((previous) => ({ ...previous, [field]: value }));

      // Clear error when user starts typing
      if (errors[field]) {
        setErrors((previous) => {
          // Use destructuring to remove the field without dynamic delete
          const { [field]: _, ...rest } = previous;
          return rest as Partial<Record<keyof T, string>>;
        });
      }

      // Optionally validate on change
      if (validateOnChange) {
        const validator = validators[field];
        if (validator) {
          const error = validator(value, { ...values, [field]: value });
          if (error) {
            setErrors((previous) => ({ ...previous, [field]: error }));
          }
        }
      }
    },
    [errors, validateOnChange, validators, values]
  );

  /**
   * Handle input blur
   */
  const handleBlur = useCallback(
    (field: keyof T) => () => {
      setTouched((previous) => ({ ...previous, [field]: true }));

      // Validate on blur
      if (validateOnBlur) {
        const error = validateField(field);
        if (error) {
          setErrors((previous) => ({ ...previous, [field]: error }));
        }
      }
    },
    [validateOnBlur, validateField]
  );

  /**
   * Handle form submission
   */
  const handleSubmit = useCallback(
    async (e: React.FormEvent): Promise<void> => {
      e.preventDefault();

      // Mark all fields as touched
      const allTouched = Object.fromEntries(
        Object.keys(initialValues).map((key) => [key, true])
      ) as Record<keyof T, boolean>;
      setTouched(allTouched);

      // Validate all fields
      if (!validateForm()) {
        return;
      }

      // Submit
      try {
        setIsSubmitting(true);
        await onSubmit(values);
      } finally {
        setIsSubmitting(false);
      }
    },
    [initialValues, validateForm, onSubmit, values]
  );

  /**
   * Manually set a field value
   */
  const setFieldValue = useCallback(<K extends keyof T>(field: K, value: T[K]) => {
    setValues((previous) => ({ ...previous, [field]: value }));
  }, []);

  /**
   * Manually set a field error
   */
  const setFieldError = useCallback((field: keyof T, error: string | null) => {
    if (error) {
      setErrors((previous) => ({ ...previous, [field]: error }));
    } else {
      setErrors((previous) => {
        // Use destructuring to remove the field without dynamic delete
        const { [field]: _, ...rest } = previous;
        return rest as Partial<Record<keyof T, string>>;
      });
    }
  }, []);

  /**
   * Reset form to initial state
   */
  const resetForm = useCallback(() => {
    setValues(initialValues);
    setErrors({});
    setTouched({});
    setIsSubmitting(false);
  }, [initialValues]);

  return {
    values,
    errors,
    touched,
    isSubmitting,
    isValid,
    handleChange,
    handleBlur,
    handleSubmit,
    setFieldValue,
    setFieldError,
    resetForm,
    validateField,
    validateForm
  };
}
