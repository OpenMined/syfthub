import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';

interface StatusMessageProps {
  readonly type: 'success' | 'error';
  readonly message: string | null;
}

const variants = {
  success: {
    container:
      'flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 dark:border-green-800 dark:bg-green-950',
    icon: 'h-4 w-4 text-green-600 dark:text-green-400',
    text: 'text-sm text-green-800 dark:text-green-200'
  },
  error: {
    container:
      'flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950',
    icon: 'h-4 w-4 text-red-600 dark:text-red-400',
    text: 'text-sm text-red-800 dark:text-red-200'
  }
} as const;

export function StatusMessage({ type, message }: StatusMessageProps) {
  const Icon = type === 'success' ? Check : AlertCircle;
  const style = variants[type];

  return (
    <AnimatePresence>
      {message ? (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className={style.container}
          role='alert'
          aria-live='polite'
        >
          <Icon className={style.icon} aria-hidden='true' />
          <span className={style.text}>{message}</span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
