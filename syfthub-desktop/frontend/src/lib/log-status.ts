// Lifecycle values for RequestLogEntry.status. Mirrors the Go-side
// LogStatus* constants in sdk/golang/syfthubapi/requestlog.go; treat any
// other value (including "") as "terminal but unknown" — agent-session logs
// written before this field existed decode that way.
export const LogStatus = {
  Running: 'running',
  Completed: 'completed',
  Failed: 'failed',
  Cancelled: 'cancelled',
} as const;

export type LogStatus = typeof LogStatus[keyof typeof LogStatus];
