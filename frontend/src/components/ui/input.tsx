import * as React from 'react';

import type { VariantProps } from 'class-variance-authority';

import { cva } from 'class-variance-authority';
import { Eye, EyeOff } from 'lucide-react';

import { cn } from '@/lib/utils';

import { Button } from './button';

const inputVariants = cva(
  'flex w-full rounded-lg border px-3 py-2 text-sm transition-all file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        default:
          'border-syft-border-light bg-white shadow-sm focus:border-syft-primary focus:ring-2 focus:ring-syft-primary/10',
        error:
          'border-red-500 bg-white shadow-sm focus:border-red-500 focus:ring-2 focus:ring-red-500/10'
      },
      size: {
        default: 'h-10 px-3',
        sm: 'h-8 px-2 text-xs',
        lg: 'h-12 px-4'
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
      ...properties
    },
    reference
  ) => {
    const [isPasswordVisible, setIsPasswordVisible] = React.useState(false);
    const inputId = id || React.useId();
    const errorId = `${inputId}-error`;
    const helperTextId = `${inputId}-helper`;

    const isPassword = type === 'password';
    const inputType = isPassword && isPasswordVisible ? 'text' : type;
    const hasError = Boolean(error);
    const currentVariant = hasError ? 'error' : variant;

    const togglePasswordVisibility = () => {
      setIsPasswordVisible(!isPasswordVisible);
    };

    return (
      <div className='w-full space-y-1'>
        {label && (
          <label htmlFor={inputId} className='text-syft-primary block text-sm font-medium'>
            {label}
            {isRequired && <span className='ml-1 text-red-500'>*</span>}
          </label>
        )}

        <div className='relative'>
          {leftIcon && (
            <div className='text-syft-muted absolute top-1/2 left-3 -translate-y-1/2'>
              {leftIcon}
            </div>
          )}

          <input
            id={inputId}
            type={inputType}
            className={cn(
              inputVariants({ variant: currentVariant, size }),
              leftIcon && 'pl-10',
              (rightIcon || isPassword) && 'pr-10',
              className
            )}
            ref={reference}
            aria-invalid={hasError}
            aria-describedby={cn(error && errorId, helperText && helperTextId)}
            {...properties}
          />

          {isPassword && (
            <Button
              type='button'
              variant='ghost'
              size='icon'
              className='text-syft-muted hover:text-syft-primary absolute top-1/2 right-1 h-8 w-8 -translate-y-1/2'
              onClick={togglePasswordVisibility}
              tabIndex={-1}
            >
              {isPasswordVisible ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
            </Button>
          )}

          {rightIcon && !isPassword && (
            <div className='text-syft-muted absolute top-1/2 right-3 -translate-y-1/2'>
              {rightIcon}
            </div>
          )}
        </div>

        {error && (
          <p id={errorId} className='text-xs text-red-500' role='alert'>
            {error}
          </p>
        )}

        {helperText && !error && (
          <p id={helperTextId} className='text-syft-muted text-xs'>
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export { Input, inputVariants };
