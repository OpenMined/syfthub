import * as React from 'react';

import type { VariantProps } from 'class-variance-authority';

import { cva } from 'class-variance-authority';
import Eye from 'lucide-react/dist/esm/icons/eye';
import EyeOff from 'lucide-react/dist/esm/icons/eye-off';

import { cn } from '@/lib/utils';

import { Button } from './button';

const inputVariants = cva(
  'flex w-full rounded-lg border px-3 py-2 text-sm transition-all duration-200 file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground/70 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        default:
          'border-input bg-background/50 backdrop-blur-sm shadow-sm focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-background/80 hover:bg-background/70',
        error:
          'border-red-500 bg-background/50 backdrop-blur-sm shadow-sm focus:border-red-500 focus:ring-2 focus:ring-red-500/20'
      },
      size: {
        default: 'h-11 px-4',
        sm: 'h-9 px-3 text-xs',
        lg: 'h-13 px-5'
      }
    },
    defaultVariants: {
      variant: 'default',
      size: 'default'
    }
  }
);

interface InputProperties
  extends Omit<React.ComponentPropsWithoutRef<'input'>, 'size'>,
    VariantProps<typeof inputVariants> {
  label?: string;
  error?: string;
  helperText?: string;
  isRequired?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  /** Input mode for mobile keyboard optimization */
  inputMode?: 'none' | 'text' | 'tel' | 'url' | 'email' | 'numeric' | 'decimal' | 'search';
}

const Input = React.forwardRef<HTMLInputElement, InputProperties>(
  (
    {
      className,
      variant,
      size,
      type = 'text',
      label,
      error,
      helperText,
      isRequired,
      leftIcon,
      rightIcon,
      id,
      inputMode,
      ...properties
    },
    reference
  ) => {
    // Auto-determine inputMode based on type if not explicitly set (Web Interface Guidelines)
    const typeToInputMode: Record<string, InputProperties['inputMode']> = {
      email: 'email',
      tel: 'tel',
      url: 'url',
      number: 'numeric',
      search: 'search'
    };
    const resolvedInputMode = inputMode ?? typeToInputMode[type];
    const [isPasswordVisible, setIsPasswordVisible] = React.useState(false);
    const inputId = id ?? React.useId();
    const errorId = `${inputId}-error`;
    const helperTextId = `${inputId}-helper`;

    const isPassword = type === 'password';
    const inputType = isPassword && isPasswordVisible ? 'text' : type;
    const hasError = Boolean(error);
    const currentVariant = hasError ? 'error' : variant;

    const togglePasswordVisibility = React.useCallback(() => {
      setIsPasswordVisible((previous) => !previous);
    }, []);

    return (
      <div className='w-full space-y-1'>
        {label ? (
          <label htmlFor={inputId} className='text-foreground block text-sm font-medium'>
            {label}
            {isRequired ? <span className='ml-1 text-red-500'>*</span> : null}
          </label>
        ) : null}

        <div className='relative'>
          {leftIcon ? (
            <div
              className='text-muted-foreground absolute top-1/2 left-3 -translate-y-1/2'
              aria-hidden='true'
            >
              {leftIcon}
            </div>
          ) : null}

          <input
            id={inputId}
            type={inputType}
            inputMode={resolvedInputMode}
            className={cn(
              inputVariants({ variant: currentVariant, size }),
              leftIcon && 'pl-10',
              (rightIcon ?? isPassword) && 'pr-10',
              className
            )}
            ref={reference}
            aria-invalid={hasError}
            aria-describedby={cn(error && errorId, helperText && helperTextId)}
            {...properties}
          />

          {isPassword ? (
            <Button
              type='button'
              variant='ghost'
              size='icon'
              className='text-muted-foreground hover:text-foreground absolute top-1/2 right-1 h-8 w-8 -translate-y-1/2'
              onClick={togglePasswordVisibility}
              tabIndex={-1}
              aria-label={isPasswordVisible ? 'Hide password' : 'Show password'}
            >
              {isPasswordVisible ? (
                <EyeOff className='h-4 w-4' aria-hidden='true' />
              ) : (
                <Eye className='h-4 w-4' aria-hidden='true' />
              )}
            </Button>
          ) : null}

          {rightIcon && !isPassword ? (
            <div
              className='text-muted-foreground absolute top-1/2 right-3 -translate-y-1/2'
              aria-hidden='true'
            >
              {rightIcon}
            </div>
          ) : null}
        </div>

        {error ? (
          <p id={errorId} className='text-xs text-red-500' role='alert'>
            {error}
          </p>
        ) : null}

        {helperText && !error ? (
          <p id={helperTextId} className='text-muted-foreground text-xs'>
            {helperText}
          </p>
        ) : null}
      </div>
    );
  }
);

Input.displayName = 'Input';

export { Input, inputVariants };
