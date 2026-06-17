import * as React from 'react';

import { motion } from 'framer-motion';
import X from 'lucide-react/dist/esm/icons/x';
import { Dialog, VisuallyHidden } from 'radix-ui';

import { cn } from '@/lib/utils';

import { Button } from './button';

interface ModalProperties {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: string;
  description?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl';
  closeOnOverlayClick?: boolean;
  showCloseButton?: boolean;
}

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl'
};

/**
 * Accessible modal dialog.
 *
 * Built on Radix `Dialog` so it composes correctly when opened from inside
 * another Radix dialog (e.g. the Settings modal). A previous hand-rolled
 * implementation portalled to `document.body` as a *sibling* of any parent
 * Radix dialog, so it inherited the parent layer's `pointer-events: none`
 * (clicks blocked) and lost focus to the parent's focus trap (typing
 * blocked) — making nested modals such as "Create New API Token" unusable.
 * Sharing Radix's layer/focus-scope stack fixes both: the nested layer
 * re-enables pointer events and pauses the parent's focus trap.
 */
export function Modal({
  isOpen,
  onClose,
  children,
  title,
  description,
  size = 'md',
  closeOnOverlayClick = true,
  showCloseButton = true
}: Readonly<ModalProperties>) {
  return (
    <Dialog.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay asChild>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className='fixed inset-0 z-50 bg-black/50 backdrop-blur-sm'
          />
        </Dialog.Overlay>

        <Dialog.Content
          // When a description is provided, Radix wires `aria-describedby` to
          // the <Dialog.Description> itself. When it isn't, explicitly passing
          // `aria-describedby={undefined}` opts out of Radix's dev advisory.
          {...(description ? {} : { 'aria-describedby': undefined })}
          onInteractOutside={(event) => {
            if (!closeOnOverlayClick) event.preventDefault();
          }}
          asChild
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ type: 'spring', duration: 0.3 }}
            className={cn(
              'border-border bg-card fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border shadow-xl',
              sizeClasses[size]
            )}
          >
            {/* A dialog must always have an accessible name. When no visible
                title is supplied, provide a visually-hidden fallback so screen
                readers (and Radix) still get a title. */}
            {title ? null : (
              <VisuallyHidden.Root>
                <Dialog.Title>Dialog</Dialog.Title>
              </VisuallyHidden.Root>
            )}

            {/* Close Button */}
            {showCloseButton ? (
              <Dialog.Close asChild>
                <Button
                  variant='ghost'
                  size='icon'
                  className='text-muted-foreground hover:text-foreground absolute top-4 right-4 z-10 h-8 w-8'
                  aria-label='Close modal'
                >
                  <X className='h-4 w-4' aria-hidden='true' />
                </Button>
              </Dialog.Close>
            ) : null}

            {/* Header */}
            {(title ?? description) ? (
              <div className='px-6 pt-6 pb-2'>
                {title ? (
                  <Dialog.Title className='font-rubik text-foreground text-xl font-medium'>
                    {title}
                  </Dialog.Title>
                ) : null}
                {description ? (
                  <Dialog.Description className='font-inter text-muted-foreground mt-1 text-sm'>
                    {description}
                  </Dialog.Description>
                ) : null}
              </div>
            ) : null}

            {/* Content */}
            <div className={cn('px-6', Boolean(title ?? description) ? 'pb-6' : 'py-6')}>
              {children}
            </div>
          </motion.div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// Simplified modal for quick use cases
interface SimpleModalProperties {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}

export function SimpleModal({
  isOpen,
  onClose,
  children,
  className
}: Readonly<SimpleModalProperties>) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} showCloseButton={false} closeOnOverlayClick={true}>
      <div className={className}>{children}</div>
    </Modal>
  );
}
