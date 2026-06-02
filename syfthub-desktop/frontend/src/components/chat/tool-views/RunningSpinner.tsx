/**
 * RunningSpinner — the small "Running…" footer shown beneath a tool view while
 * its call is still in flight. Shared by the tool-view components so the label
 * and spinner markup live in one place.
 */

import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

export function RunningSpinner() {
  return (
    <div className='text-muted-foreground flex items-center gap-1.5 px-1 text-xs'>
      <Loader2 className='h-3 w-3 animate-spin' aria-hidden='true' />
      <span>Running…</span>
    </div>
  );
}
