import { useEffect, useCallback } from 'react';
import { useAppStore, RequestLogEntry } from '../../stores/appStore';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

// Format timestamp for display
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

// Format full timestamp for tooltip/detail
function formatFullTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

// Format duration for display
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(2)}s`;
}

// Status badge component
function StatusBadge({ success }: { success: boolean }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        success
          ? 'bg-chart-2/20 text-chart-2'
          : 'bg-destructive/20 text-destructive'
      }`}
    >
      {success ? (
        <>
          <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
          OK
        </>
      ) : (
        <>
          <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
          Error
        </>
      )}
    </span>
  );
}

// Policy badge component
function PolicyBadge({ policy }: { policy: { evaluated: boolean; allowed: boolean; pending?: boolean } | null | undefined }) {
  if (!policy || !policy.evaluated) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-secondary/50 text-muted-foreground">
        N/A
      </span>
    );
  }

  if (policy.pending) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-chart-3/20 text-chart-3">
        <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
        </svg>
        Pending
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        policy.allowed
          ? 'bg-chart-2/20 text-chart-2'
          : 'bg-destructive/20 text-destructive'
      }`}
    >
      {policy.allowed ? (
        <>
          <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          Allowed
        </>
      ) : (
        <>
          <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 1.944A11.954 11.954 0 012.166 5C2.056 5.649 2 6.319 2 7c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7c0-.682-.057-1.35-.166-2.001A11.954 11.954 0 0010 1.944zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          Denied
        </>
      )}
    </span>
  );
}

// Log detail modal/panel
function LogDetailPanel({
  log,
  onClose,
}: {
  log: RequestLogEntry;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-card rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-lg font-medium text-foreground">Log Details</h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
        <div className="p-4 overflow-y-auto max-h-[calc(80vh-60px)]">
          <div className="space-y-4">
            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground uppercase">Timestamp</label>
                <p className="text-sm text-foreground">{formatFullTimestamp(log.timestamp)}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Duration</label>
                <p className="text-sm text-foreground">{log.timing ? formatDuration(log.timing.durationMs) : 'N/A'}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Correlation ID</label>
                <p className="text-sm text-secondary-foreground font-mono text-xs">{log.correlationId}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Status</label>
                <p className="text-sm">{log.response && <StatusBadge success={log.response.success} />}</p>
              </div>
            </div>

            {/* User Info */}
            {log.user && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">User</label>
                <div className="mt-1 bg-background rounded p-2">
                  <p className="text-sm text-foreground">{log.user.username || log.user.id}</p>
                  {log.user.email && <p className="text-xs text-muted-foreground">{log.user.email}</p>}
                  {log.user.role && <p className="text-xs text-muted-foreground/70">Role: {log.user.role}</p>}
                </div>
              </div>
            )}

            {/* Request */}
            {log.request && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">Request</label>
                <div className="mt-1 bg-background rounded p-2">
                  <p className="text-xs text-muted-foreground mb-1">Type: {log.request.type} | Size: {log.request.rawSize} bytes</p>
                  {log.request.query && (
                    <pre className="text-sm text-foreground whitespace-pre-wrap break-words">{log.request.query}</pre>
                  )}
                  {log.request.messages && log.request.messages.length > 0 && (
                    <div className="space-y-2">
                      {log.request.messages.map((msg: { role: string; content: string }, i: number) => (
                        <div key={i} className="border-l-2 border-border pl-2">
                          <span className="text-xs font-medium text-muted-foreground">{msg.role}</span>
                          <p className="text-sm text-foreground whitespace-pre-wrap break-words">{msg.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Response */}
            {log.response && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">Response</label>
                <div className="mt-1 bg-background rounded p-2">
                  {log.response.success ? (
                    <>
                      {log.response.content && (
                        <pre className="text-sm text-foreground whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                          {log.response.content}
                          {log.response.contentTruncated && (
                            <span className="text-muted-foreground"> ... (truncated)</span>
                          )}
                        </pre>
                      )}
                    </>
                  ) : (
                    <div className="text-destructive">
                      <p className="text-sm font-medium">{log.response.errorCode || 'Error'}</p>
                      <p className="text-sm">{log.response.error}</p>
                      {log.response.errorType && (
                        <p className="text-xs text-muted-foreground">Type: {log.response.errorType}</p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Policy */}
            {log.policy && log.policy.evaluated && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">Policy</label>
                <div className="mt-1 bg-background rounded p-2">
                  <div className="flex items-center gap-2 mb-1">
                    <PolicyBadge policy={log.policy} />
                    {log.policy.policyName && (
                      <span className="text-xs text-muted-foreground">{log.policy.policyName}</span>
                    )}
                  </div>
                  {log.policy.reason && (
                    <p className="text-sm text-secondary-foreground">{log.policy.reason}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Empty state
function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center text-muted-foreground">
      <div className="text-center">
        <svg
          className="w-12 h-12 mx-auto mb-3 opacity-30"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <h3 className="text-sm font-medium text-foreground mb-1">No Logs Yet</h3>
        <p className="text-xs">Logs will appear here when requests are made to this endpoint</p>
      </div>
    </div>
  );
}

// Main LogsTab component
export function LogsTab() {
  const {
    selectedEndpointSlug,
    logs,
    logStats,
    logsLoading,
    logsHasMore,
    selectedLog,
    fetchLogs,
    fetchLogStats,
    loadMoreLogs,
    setSelectedLog,
  } = useAppStore();

  const { logsStatusFilter, setLogsStatusFilter } = useAppStore();

  // Fetch logs and stats when endpoint changes
  useEffect(() => {
    if (selectedEndpointSlug) {
      fetchLogs(logsStatusFilter === 'all' ? '' : logsStatusFilter);
      fetchLogStats();
    }
  }, [selectedEndpointSlug, fetchLogs, fetchLogStats, logsStatusFilter]);

  // Handle refresh
  const handleRefresh = useCallback(() => {
    if (selectedEndpointSlug) {
      fetchLogs(logsStatusFilter === 'all' ? '' : logsStatusFilter);
      fetchLogStats();
    }
  }, [selectedEndpointSlug, fetchLogs, fetchLogStats, logsStatusFilter]);

  // Handle load more
  const handleLoadMore = useCallback(() => {
    loadMoreLogs(logsStatusFilter === 'all' ? '' : logsStatusFilter);
  }, [loadMoreLogs, logsStatusFilter]);

  if (!selectedEndpointSlug) {
    return <EmptyState />;
  }

  // Show centered empty state when no logs
  if (logs.length === 0 && !logsLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        <div className="text-center">
          <svg
            className="w-12 h-12 mx-auto mb-3 opacity-30"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <h3 className="text-sm font-medium text-foreground mb-1">No Logs Yet</h3>
          <p className="text-xs mb-4">Logs will appear here when requests are made to this endpoint</p>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            disabled={logsLoading}
            className="h-7 px-3 text-xs"
          >
            <svg
              className={`w-4 h-4 mr-1 ${logsLoading ? 'animate-spin' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            Refresh
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header with filters and stats */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-border/50 bg-card/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* Status filter */}
            <Select value={logsStatusFilter} onValueChange={setLogsStatusFilter}>
              <SelectTrigger size="sm" className="w-[130px] h-7 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel>Filter by</SelectLabel>
                  <SelectItem value="all" className="text-xs">All Requests</SelectItem>
                  <SelectItem value="success" className="text-xs">Success Only</SelectItem>
                  <SelectItem value="error" className="text-xs">Errors Only</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>

            {/* Stats summary */}
            {logStats && (
              <div className="flex items-center gap-3 text-xs text-muted-foreground ml-2">
                <span>{logStats.totalRequests} total</span>
                <span className="text-chart-2">{logStats.successCount} success</span>
                <span className="text-destructive">{logStats.errorCount} errors</span>
                {logStats.avgDurationMs > 0 && (
                  <span>Avg: {formatDuration(logStats.avgDurationMs)}</span>
                )}
              </div>
            )}
          </div>

          {/* Refresh button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            disabled={logsLoading}
            className="h-7 px-2 text-xs"
          >
            <svg
              className={`w-4 h-4 mr-1 ${logsLoading ? 'animate-spin' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            Refresh
          </Button>
        </div>
      </div>

      {/* Logs table */}
      <div className="flex-1 overflow-auto">
        {logsLoading && logs.length === 0 ? (
          <div className="flex-1 flex items-center justify-center py-12">
            <div className="text-center text-muted-foreground">
              <svg className="w-8 h-8 mx-auto mb-2 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <p className="text-xs">Loading logs...</p>
            </div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-card/50 sticky top-0">
              <tr className="text-left text-xs text-muted-foreground uppercase">
                <th className="px-4 py-2 font-medium">Time</th>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Duration</th>
                <th className="px-4 py-2 font-medium">Policy</th>
                <th className="px-4 py-2 font-medium w-16"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {logs.map((log) => (
                <tr
                  key={log.id}
                  className="hover:bg-card/30 cursor-pointer"
                  onClick={() => setSelectedLog(log)}
                >
                  <td className="px-4 py-2 text-secondary-foreground">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span>{formatTimestamp(log.timestamp)}</span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        <p>{formatFullTimestamp(log.timestamp)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </td>
                  <td className="px-4 py-2 text-secondary-foreground">
                    {log.user?.username || log.user?.id || 'Unknown'}
                  </td>
                  <td className="px-4 py-2">
                    {log.response && <StatusBadge success={log.response.success} />}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {log.timing ? formatDuration(log.timing.durationMs) : '-'}
                  </td>
                  <td className="px-4 py-2">
                    <PolicyBadge policy={log.policy} />
                  </td>
                  <td className="px-4 py-2">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button className="text-muted-foreground hover:text-foreground p-1">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="left">
                        <p>View details</p>
                      </TooltipContent>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Load more button */}
        {logsHasMore && (
          <div className="p-4 text-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLoadMore}
              disabled={logsLoading}
              className="text-xs"
            >
              {logsLoading ? 'Loading...' : 'Load More'}
            </Button>
          </div>
        )}
      </div>

      {/* Log detail modal */}
      {selectedLog && (
        <LogDetailPanel log={selectedLog} onClose={() => setSelectedLog(null)} />
      )}
    </div>
  );
}
