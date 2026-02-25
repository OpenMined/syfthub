import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';

interface StatusMessageAction {
  readonly label: string;
  readonly onClick: () => void;
}

interface StatusMessageProps {
  readonly type: 'success' | 'error';
  readonly message: string | null;
  readonly action?: StatusMessageAction;
}

const variants = {
  success: {
    container:
      'flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 dark:border-green-800 dark:bg-green-950',
    icon: 'h-4 w-4 text-green-600 dark:text-green-400',
    text: 'text-sm text-green-800 dark:text-green-200',
    actionClass:
      'ml-auto h-7 text-green-700 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300'
  },
  error: {
    container:
      'flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950',
    icon: 'h-4 w-4 text-red-600 dark:text-red-400',
    text: 'text-sm text-red-800 dark:text-red-200',
    actionClass:
      'ml-auto h-7 text-red-700 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300'
  }
} as const;

export function StatusMessage({ type, message, action }: StatusMessageProps) {
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
          {action ? (
            <button
              type='button'
              onClick={action.onClick}
              className={`${style.actionClass} cursor-pointer bg-transparent text-xs font-medium`}
            >
              {action.label}
            </button>
          ) : null}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
