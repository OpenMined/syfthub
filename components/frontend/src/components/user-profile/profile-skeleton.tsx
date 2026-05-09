/**
 * Loading skeleton for the public user profile page.
 *
 * Mirrors the layout of profile-hero + stats-strip + endpoints-list so the
 * page doesn't shift when data resolves.
 */
export function ProfileSkeleton() {
  return (
    <div className='bg-background min-h-screen' role='status' aria-label='Loading user profile'>
      {/* Hero band */}
      <div className='border-border bg-card border-b'>
        <div className='mx-auto max-w-5xl px-6 py-8'>
          <div className='flex flex-col gap-6 sm:flex-row sm:items-center'>
            <div className='bg-muted h-24 w-24 flex-shrink-0 animate-pulse rounded-full' />
            <div className='flex-1 space-y-3'>
              <div className='bg-muted h-8 w-64 animate-pulse rounded' />
              <div className='bg-muted h-4 w-40 animate-pulse rounded' />
              <div className='bg-muted h-4 w-80 animate-pulse rounded' />
            </div>
          </div>
        </div>
      </div>

      {/* Stats strip */}
      <div className='border-border bg-background border-b'>
        <div className='mx-auto flex max-w-5xl flex-wrap gap-8 px-6 py-4'>
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className='space-y-2'>
              <div className='bg-muted h-3 w-16 animate-pulse rounded' />
              <div className='bg-muted h-5 w-12 animate-pulse rounded' />
            </div>
          ))}
        </div>
      </div>

      {/* List */}
      <div className='mx-auto max-w-5xl px-6 py-8'>
        <div className='bg-muted mb-6 h-9 w-72 animate-pulse rounded' />
        <div className='border-border bg-card divide-border divide-y rounded-xl border'>
          {[0, 1, 2, 3, 4].map((index) => (
            <div key={index} className='flex items-center gap-4 p-4'>
              <div className='bg-muted h-5 w-5 flex-shrink-0 animate-pulse rounded' />
              <div className='flex-1 space-y-2'>
                <div className='bg-muted h-4 w-48 animate-pulse rounded' />
                <div className='bg-muted h-3 w-72 animate-pulse rounded' />
              </div>
              <div className='bg-muted h-4 w-20 animate-pulse rounded' />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
