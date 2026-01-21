import * as React from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import X from 'lucide-react/dist/esm/icons/x';

import { cn } from '@/lib/utils';

import { Button } from './button';

interface ModalProperties {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: string;
  description?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeOnOverlayClick?: boolean;
  showCloseButton?: boolean;
}

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl'
};

// Selector for focusable elements
const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]):not([disabled])';

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
  const modalReference = React.useRef<HTMLDivElement>(null);
  const previousActiveElement = React.useRef<Element | null>(null);

  // Handle focus management: store previous element, focus first element, restore on close
  React.useEffect(() => {
    if (isOpen) {
      // Store the currently focused element
      previousActiveElement.current = document.activeElement;

      // Focus the first focusable element in modal after a short delay
      // (allows animation to start)
      const timeoutId = setTimeout(() => {
        const focusableElements = modalReference.current?.querySelectorAll(FOCUSABLE_SELECTOR);
        if (focusableElements?.length) {
          (focusableElements[0] as HTMLElement).focus();
        }
      }, 50);

      return () => {
        clearTimeout(timeoutId);
      };
    } else {
      // Restore focus when modal closes
      if (previousActiveElement.current instanceof HTMLElement) {
        previousActiveElement.current.focus();
      }
    }
  }, [isOpen]);

  // Handle escape key and body scroll
  React.useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  // Handle Tab key for focus trapping
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== 'Tab') return;

    const nodeList = modalReference.current?.querySelectorAll(FOCUSABLE_SELECTOR);
    if (!nodeList?.length) return;

    const focusableElements = [...nodeList] as HTMLElement[];
    const firstElement = focusableElements[0];
    const lastElement = focusableElements.at(-1);
    if (!firstElement || !lastElement) return;

    // Shift + Tab: if on first element, wrap to last
    if (event.shiftKey && document.activeElement === (firstElement as Element)) {
      event.preventDefault();
      lastElement.focus();
    }
    // Tab: if on last element, wrap to first
    else if (!event.shiftKey && document.activeElement === (lastElement as Element)) {
      event.preventDefault();
      firstElement.focus();
    }
  };

  const handleOverlayClick = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget && closeOnOverlayClick) {
      onClose();
    }
  };

  return (
    <AnimatePresence>
      {isOpen ? (
        <div
          className='fixed inset-0 z-50 flex items-center justify-center p-4'
          onKeyDown={handleKeyDown}
        >
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className='absolute inset-0 bg-black/50 backdrop-blur-sm'
            onClick={handleOverlayClick}
          />

          {/* Modal Content */}
          <motion.div
            ref={modalReference}
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', duration: 0.3 }}
            className={cn(
              'border-syft-border relative w-full rounded-xl border bg-white shadow-xl',
              sizeClasses[size]
            )}
            role='dialog'
            aria-modal='true'
            aria-labelledby={title ? 'modal-title' : undefined}
            aria-describedby={description ? 'modal-description' : undefined}
          >
            {/* Close Button */}
            {showCloseButton ? (
              <Button
                variant='ghost'
                size='icon'
                className='text-syft-muted hover:text-syft-primary absolute top-4 right-4 z-10 h-8 w-8'
                onClick={onClose}
                aria-label='Close modal'
              >
                <X className='h-4 w-4' aria-hidden='true' />
              </Button>
            ) : null}

            {/* Header */}
            {(title ?? description) ? (
              <div className='px-6 pt-6 pb-2'>
                {title ? (
                  <h2 id='modal-title' className='font-rubik text-syft-primary text-xl font-medium'>
                    {title}
                  </h2>
                ) : null}
                {description ? (
                  <p id='modal-description' className='font-inter text-syft-muted mt-1 text-sm'>
                    {description}
                  </p>
                ) : null}
              </div>
            ) : null}

            {/* Content */}
            <div className={cn('px-6', Boolean(title ?? description) ? 'pb-6' : 'py-6')}>
              {children}
            </div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
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
