import { z } from 'zod';

// Shared field schemas
const emailField = z
  .string()
  .min(1, 'Email is required')
  .max(254, 'Please enter a valid email address')
  .regex(/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/, 'Please enter a valid email address');

const otpCodeField = z
  .string()
  .min(1, 'Verification code is required')
  .length(6, 'Code must be 6 digits')
  .regex(/^\d{6}$/, 'Code must be 6 digits');

const passwordField = z
  .string()
  .min(1, 'Password is required')
  .min(6, 'Password must be at least 6 characters')
  .regex(/\d/, 'Password must contain at least one digit')
  .regex(/[a-zA-Z]/, 'Password must contain at least one letter');

export const loginSchema = z.object({
  email: emailField,
  password: z
    .string()
    .min(1, 'Password is required')
    .min(6, 'Password must be at least 6 characters')
});

export type LoginFormValues = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    name: z
      .string()
      .min(1, 'Name is required')
      .min(2, 'Name must be at least 2 characters')
      .max(50, 'Name must be less than 50 characters'),
    email: emailField,
    password: passwordField,
    confirmPassword: z.string().min(1, 'Please confirm your password'),
    accountingPassword: z.string(),
    termsAccepted: z.boolean().refine((value) => value, {
      message: 'You must accept the terms to continue'
    })
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword']
  });

export type RegisterFormValues = z.infer<typeof registerSchema>;

export const profileSchema = z.object({
  username: z
    .string()
    .min(3, 'Username must be at least 3 characters')
    .max(39, 'Username must be 39 characters or less')
    .regex(
      /^[a-zA-Z][\w-]*$/,
      'Username must start with a letter and contain only letters, numbers, hyphens, or underscores'
    ),
  displayName: z.string().max(50, 'Display name must be less than 50 characters'),
  email: emailField,
  avatarUrl: z.string()
});

export type ProfileFormValues = z.infer<typeof profileSchema>;

export const verifyOtpSchema = z.object({
  code: otpCodeField
});

export type VerifyOtpFormValues = z.infer<typeof verifyOtpSchema>;

export const passwordResetRequestSchema = z.object({
  email: emailField
});

export type PasswordResetRequestFormValues = z.infer<typeof passwordResetRequestSchema>;

export const passwordResetConfirmSchema = z
  .object({
    code: otpCodeField,
    newPassword: passwordField,
    confirmPassword: z.string().min(1, 'Please confirm your password')
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword']
  });

export type PasswordResetConfirmFormValues = z.infer<typeof passwordResetConfirmSchema>;
