/**
 * Compact progress/status indicator.
 */

interface AgentStatusBadgeProps {
  readonly status: string;
  readonly detail: string;
  readonly progress?: number;
  readonly isActive?: boolean;
}

export function AgentStatusBadge({
  status,
  detail,
  progress,
  isActive = false
}: AgentStatusBadgeProps) {
  return (
    <div className='flex items-center gap-2 px-1 py-1'>
      {isActive ? (
        <div className='h-3 w-3 animate-spin rounded-full border-2 border-blue-500 border-t-transparent' />
      ) : (
        <div className='bg-muted-foreground/30 mx-[3px] h-1.5 w-1.5 rounded-full' />
      )}
      <span className='text-muted-foreground text-xs font-medium'>{status}</span>
      {detail && <span className='text-muted-foreground text-xs'>{detail}</span>}
      {progress != null && (
        <div className='bg-muted h-1.5 w-16 rounded-full'>
          <div
            className='h-full rounded-full bg-blue-500 transition-all'
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
