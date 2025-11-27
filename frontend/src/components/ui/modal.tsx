import * as React from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';

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
  // Handle escape key
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

  const handleOverlayClick = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget && closeOnOverlayClick) {
      onClose();
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className='fixed inset-0 z-50 flex items-center justify-center p-4'>
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
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', duration: 0.3 }}
            className={cn(
              'relative w-full rounded-xl border border-[#ecebef] bg-white shadow-xl',
              sizeClasses[size]
            )}
            role='dialog'
            aria-modal='true'
            aria-labelledby={title ? 'modal-title' : undefined}
            aria-describedby={description ? 'modal-description' : undefined}
          >
            {/* Close Button */}
            {showCloseButton && (
              <Button
                variant='ghost'
                size='icon'
                className='absolute top-4 right-4 z-10 h-8 w-8 text-[#5e5a72] hover:text-[#272532]'
                onClick={onClose}
                aria-label='Close modal'
              >
                <X className='h-4 w-4' />
              </Button>
            )}

            {/* Header */}
            {(title || description) && (
              <div className='px-6 pt-6 pb-2'>
                {title && (
                  <h2 id='modal-title' className='font-rubik text-xl font-medium text-[#272532]'>
                    {title}
                  </h2>
                )}
                {description && (
                  <p id='modal-description' className='font-inter mt-1 text-sm text-[#5e5a72]'>
                    {description}
                  </p>
                )}
              </div>
            )}

            {/* Content */}
            <div className={cn('px-6', title || description ? 'pb-6' : 'py-6')}>{children}</div>
          </motion.div>
        </div>
      )}
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
