import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useForm } from '../use-form';

describe('useForm', () => {
  const defaultOptions = {
    initialValues: { email: '', password: '' },
    onSubmit: vi.fn()
  };

  it('initializes with provided values', () => {
    const { result } = renderHook(() => useForm(defaultOptions));
    expect(result.current.values).toEqual({ email: '', password: '' });
    expect(result.current.errors).toEqual({});
    expect(result.current.touched).toEqual({});
    expect(result.current.isSubmitting).toBe(false);
    expect(result.current.isValid).toBe(true);
  });

  it('handleChange updates value and clears error', () => {
    const { result } = renderHook(() =>
      useForm({
        ...defaultOptions,
        validators: {
          email: (v: string) => (v ? null : 'Required')
        }
      })
    );

    // First set an error by validating
    act(() => {
      result.current.validateForm();
    });
    expect(result.current.errors.email).toBe('Required');

    // Now change value - should clear error
    act(() => {
      result.current.handleChange('email')({
        target: { value: 'test@test.com' }
      } as React.ChangeEvent<HTMLInputElement>);
    });
    expect(result.current.values.email).toBe('test@test.com');
    expect(result.current.errors.email).toBeUndefined();
  });

  it('handleBlur marks field as touched and validates', () => {
    const { result } = renderHook(() =>
      useForm({
        ...defaultOptions,
        validators: {
          email: (v: string) => (v ? null : 'Email is required')
        },
        validateOnBlur: true
      })
    );

    act(() => {
      result.current.handleBlur('email')();
    });

    expect(result.current.touched.email).toBe(true);
    expect(result.current.errors.email).toBe('Email is required');
  });

  it('validateOnChange mode validates on input change', () => {
    const { result } = renderHook(() =>
      useForm({
        ...defaultOptions,
        validators: {
          email: (v: string) => (v.length < 3 ? 'Too short' : null)
        },
        validateOnChange: true
      })
    );

    act(() => {
      result.current.handleChange('email')({
        target: { value: 'ab' }
      } as React.ChangeEvent<HTMLInputElement>);
    });

    expect(result.current.errors.email).toBe('Too short');

    act(() => {
      result.current.handleChange('email')({
        target: { value: 'valid@email.com' }
      } as React.ChangeEvent<HTMLInputElement>);
    });

    expect(result.current.errors.email).toBeUndefined();
  });

  it('handleSubmit validates all fields and calls onSubmit if valid', async () => {
    const onSubmit = vi.fn();
    const { result } = renderHook(() =>
      useForm({
        initialValues: { email: 'test@test.com' },
        validators: {
          email: (v: string) => (v ? null : 'Required')
        },
        onSubmit
      })
    );

    await act(async () => {
      await result.current.handleSubmit({
        preventDefault: vi.fn()
      } as unknown as React.FormEvent);
    });

    expect(onSubmit).toHaveBeenCalledWith({ email: 'test@test.com' });
  });

  it('handleSubmit prevents submission if validation fails', async () => {
    const onSubmit = vi.fn();
    const { result } = renderHook(() =>
      useForm({
        initialValues: { email: '' },
        validators: {
          email: (v: string) => (v ? null : 'Required')
        },
        onSubmit
      })
    );

    await act(async () => {
      await result.current.handleSubmit({
        preventDefault: vi.fn()
      } as unknown as React.FormEvent);
    });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(result.current.errors.email).toBe('Required');
  });

  it('handleSubmit manages isSubmitting state', async () => {
    let resolveSubmit: () => void;
    const submitPromise = new Promise<void>((resolve) => {
      resolveSubmit = resolve;
    });
    const onSubmit = vi.fn(() => submitPromise);
    const { result } = renderHook(() =>
      useForm({
        initialValues: { email: 'test@test.com' },
        onSubmit
      })
    );

    let submitDone: Promise<void>;
    act(() => {
      submitDone = result.current.handleSubmit({
        preventDefault: vi.fn()
      } as unknown as React.FormEvent);
    });

    expect(result.current.isSubmitting).toBe(true);

    await act(async () => {
      resolveSubmit();
      await submitDone;
    });

    expect(result.current.isSubmitting).toBe(false);
  });

  it('setFieldValue updates a specific field', () => {
    const { result } = renderHook(() => useForm(defaultOptions));

    act(() => {
      result.current.setFieldValue('email', 'new@email.com');
    });

    expect(result.current.values.email).toBe('new@email.com');
  });

  it('setFieldError sets and clears errors', () => {
    const { result } = renderHook(() => useForm(defaultOptions));

    act(() => {
      result.current.setFieldError('email', 'Custom error');
    });
    expect(result.current.errors.email).toBe('Custom error');

    act(() => {
      result.current.setFieldError('email', null);
    });
    expect(result.current.errors.email).toBeUndefined();
  });

  it('resetForm restores initial state', () => {
    const { result } = renderHook(() => useForm(defaultOptions));

    // Modify state
    act(() => {
      result.current.setFieldValue('email', 'modified@test.com');
      result.current.setFieldError('password', 'Error');
    });

    // Reset
    act(() => {
      result.current.resetForm();
    });

    expect(result.current.values).toEqual({ email: '', password: '' });
    expect(result.current.errors).toEqual({});
    expect(result.current.touched).toEqual({});
    expect(result.current.isSubmitting).toBe(false);
  });

  it('validateField returns error for single field', () => {
    const { result } = renderHook(() =>
      useForm({
        ...defaultOptions,
        validators: {
          email: (v: string) => (v ? null : 'Required')
        }
      })
    );

    expect(result.current.validateField('email')).toBe('Required');
    expect(result.current.validateField('password')).toBeNull();
  });

  it('validateForm returns true when all fields valid', () => {
    const { result } = renderHook(() =>
      useForm({
        initialValues: { email: 'test@test.com' },
        validators: {
          email: (v: string) => (v ? null : 'Required')
        },
        onSubmit: vi.fn()
      })
    );

    let isValid = false;
    act(() => {
      isValid = result.current.validateForm();
    });

    expect(isValid).toBe(true);
  });
});
