/**
 * Structured logging for frontend.
 *
 * Provides consistent log formatting with correlation IDs
 * and structured context for debugging.
 */

import { getCorrelationId } from './correlation';

/** Log levels */
export enum LogLevel {
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error'
}

/** Context object for structured logging */
export type LogContext = Record<string, unknown>;

/** Structured log entry */
interface LogEntry {
  timestamp: string;
  level: LogLevel;
  event: string;
  correlationId: string | null;
  context?: LogContext;
  error?: {
    type: string;
    message: string;
    stack?: string;
  };
}

/**
 * Check if we're in development mode.
 */
function isDevelopment(): boolean {
  return import.meta.env.DEV;
}

/**
 * Format a log entry for console output.
 */
function formatLogEntry(entry: LogEntry): string {
  const parts = [
    `[${entry.timestamp}]`,
    `[${entry.level.toUpperCase()}]`,
    entry.correlationId ? `[${entry.correlationId.slice(0, 8)}]` : '',
    entry.event
  ].filter(Boolean);

  return parts.join(' ');
}

/**
 * Create a structured log entry.
 */
function createLogEntry(
  level: LogLevel,
  event: string,
  context?: LogContext,
  error?: Error
): LogEntry {
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    event,
    correlationId: getCorrelationId()
  };

  if (context && Object.keys(context).length > 0) {
    entry.context = context;
  }

  if (error) {
    entry.error = {
      type: error.name,
      message: error.message,
      stack: error.stack
    };
  }

  return entry;
}

/**
 * Log to console in development, optionally with structured data.
 */
function logToConsole(level: LogLevel, entry: LogEntry): void {
  // In production, we might want to be less verbose
  // but still log errors
  if (!isDevelopment() && level !== LogLevel.ERROR && level !== LogLevel.WARN) {
    return;
  }

  const message = formatLogEntry(entry);
  const data = entry.context || entry.error ? entry : undefined;

  switch (level) {
    case LogLevel.DEBUG: {
      if (data) console.debug(message, data);
      else console.debug(message);
      break;
    }
    case LogLevel.INFO: {
      if (data) console.info(message, data);
      else console.info(message);
      break;
    }
    case LogLevel.WARN: {
      if (data) console.warn(message, data);
      else console.warn(message);
      break;
    }
    case LogLevel.ERROR: {
      if (data) console.error(message, data);
      else console.error(message);
      break;
    }
  }
}

/**
 * Structured logger for frontend.
 *
 * @example
 * logger.info('user.login.success', { userId: '123' });
 * logger.error('api.request.failed', { endpoint: '/users' }, error);
 */
export const logger = {
  /**
   * Log a debug message.
   */
  debug(event: string, context?: LogContext): void {
    const entry = createLogEntry(LogLevel.DEBUG, event, context);
    logToConsole(LogLevel.DEBUG, entry);
  },

  /**
   * Log an info message.
   */
  info(event: string, context?: LogContext): void {
    const entry = createLogEntry(LogLevel.INFO, event, context);
    logToConsole(LogLevel.INFO, entry);
  },

  /**
   * Log a warning message.
   */
  warn(event: string, context?: LogContext, error?: Error): void {
    const entry = createLogEntry(LogLevel.WARN, event, context, error);
    logToConsole(LogLevel.WARN, entry);
  },

  /**
   * Log an error message.
   */
  error(event: string, context?: LogContext, error?: Error): void {
    const entry = createLogEntry(LogLevel.ERROR, event, context, error);
    logToConsole(LogLevel.ERROR, entry);
  }
};
