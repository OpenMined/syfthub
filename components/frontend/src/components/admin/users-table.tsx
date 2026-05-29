import { useEffect, useMemo, useState } from 'react';

import type {
  AdminUserRow,
  AdminUserSortBy,
  AdminUsersQuery,
  SortDir,
  UserRole
} from '@/lib/types';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import ArrowDown from 'lucide-react/dist/esm/icons/arrow-down';
import ArrowUp from 'lucide-react/dist/esm/icons/arrow-up';
import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import ChevronsUpDown from 'lucide-react/dist/esm/icons/chevrons-up-down';
import Download from 'lucide-react/dist/esm/icons/download';
import Inbox from 'lucide-react/dist/esm/icons/inbox';
import Search from 'lucide-react/dist/esm/icons/search';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Pagination,
  PaginationButton,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationNext,
  PaginationPrevious
} from '@/components/ui/pagination';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { downloadUsersCsv, useAdminUsers } from '@/hooks/use-admin-api';
import { formatDate, formatRelativeTime } from '@/lib/date-utils';
import { cn } from '@/lib/utils';

const PAGE_SIZE = 20;

interface SortableColumn {
  key: AdminUserSortBy;
  label: string;
  className?: string;
}

const SORTABLE_COLUMNS: SortableColumn[] = [
  { key: 'username', label: 'User' },
  { key: 'email', label: 'Email' },
  { key: 'role', label: 'Role' },
  { key: 'last_login_at', label: 'Last login' },
  { key: 'created_at', label: 'Joined' }
];

/** Map a sort direction to the matching `aria-sort` token. */
function ariaSortValue(active: boolean, dir: SortDir): 'ascending' | 'descending' | 'none' {
  if (!active) return 'none';
  return dir === 'asc' ? 'ascending' : 'descending';
}

type PageEntry = number | 'ellipsis-left' | 'ellipsis-right';

/**
 * Build the compact list of page numbers to render, with ellipsis gaps. Gaps
 * are tagged by side so each entry has a stable React key (there are at most
 * two gaps — one before and one after the current-page window).
 */
function pageWindow(current: number, total: number): PageEntry[] {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const pages = new Set<number>([1, total, current, current - 1, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).toSorted((a, b) => a - b);
  const result: PageEntry[] = [];
  let previous = 0;
  for (const page of sorted) {
    if (previous && page - previous > 1) {
      result.push(page <= current ? 'ellipsis-left' : 'ellipsis-right');
    }
    result.push(page);
    previous = page;
  }
  return result;
}

const ROLE_VARIANT: Record<UserRole, 'default' | 'secondary' | 'outline'> = {
  admin: 'default',
  user: 'secondary',
  guest: 'outline'
};

/** A small "yes/no" badge with an icon, used for active + verified columns. */
function StatusBadge({ ok, yes, no }: Readonly<{ ok: boolean; yes: string; no: string }>) {
  return (
    <Badge variant={ok ? 'secondary' : 'outline'} className='gap-1 font-normal'>
      {ok ? (
        <CheckCircle2 className='text-primary size-3.5' aria-hidden='true' />
      ) : (
        <AlertCircle className='text-muted-foreground size-3.5' aria-hidden='true' />
      )}
      {ok ? yes : no}
    </Badge>
  );
}

/** The sortable column header button, wired to drive `sort_by` / `sort_dir`. */
function SortHeader({
  column,
  activeKey,
  dir,
  onSort
}: Readonly<{
  column: SortableColumn;
  activeKey: AdminUserSortBy;
  dir: SortDir;
  onSort: (key: AdminUserSortBy) => void;
}>) {
  const isActive = activeKey === column.key;
  let Icon = ChevronsUpDown;
  if (isActive) Icon = dir === 'asc' ? ArrowUp : ArrowDown;
  return (
    <th
      scope='col'
      aria-sort={ariaSortValue(isActive, dir)}
      className={cn('px-4 py-3 text-left font-medium', column.className)}
    >
      <button
        type='button'
        onClick={() => {
          onSort(column.key);
        }}
        className='text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 -mx-1 inline-flex items-center gap-1 rounded px-1 focus-visible:ring-[3px] focus-visible:outline-none'
      >
        {column.label}
        <Icon
          className={cn('size-3.5', isActive ? 'text-foreground' : 'opacity-50')}
          aria-hidden='true'
        />
      </button>
    </th>
  );
}

type RoleFilter = UserRole | 'all';
type TriStateFilter = 'all' | 'true' | 'false';

/** Coerce the tri-state filter into the optional boolean the API expects. */
function triToBool(value: TriStateFilter): boolean | undefined {
  if (value === 'all') return undefined;
  return value === 'true';
}

/**
 * Sortable, filterable, paginated admin users table. Owns its own query state
 * (page / sort / search / filters) and reads data through `useAdminUsers`.
 */
export function UsersTable() {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<AdminUserSortBy>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all');
  const [activeFilter, setActiveFilter] = useState<TriStateFilter>('all');
  const [verifiedFilter, setVerifiedFilter] = useState<TriStateFilter>('all');
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // Debounce the search box so each keystroke doesn't fire a request.
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => {
      clearTimeout(handle);
    };
  }, [searchInput]);

  const query = useMemo<AdminUsersQuery>(
    () => ({
      page,
      page_size: PAGE_SIZE,
      sort_by: sortBy,
      sort_dir: sortDir,
      search: search || undefined,
      role: roleFilter === 'all' ? undefined : roleFilter,
      is_active: triToBool(activeFilter),
      is_email_verified: triToBool(verifiedFilter)
    }),
    [page, sortBy, sortDir, search, roleFilter, activeFilter, verifiedFilter]
  );

  const { data, isLoading, isFetching, isError, error } = useAdminUsers(query);

  function handleSort(key: AdminUserSortBy) {
    if (key === sortBy) {
      setSortDir((previous) => (previous === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(key);
      setSortDir(key === 'username' || key === 'email' || key === 'role' ? 'asc' : 'desc');
    }
    setPage(1);
  }

  function resetToFirstPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  async function handleExport() {
    setExportError(null);
    setIsExporting(true);
    try {
      await downloadUsersCsv(query);
    } catch (error_) {
      setExportError(error_ instanceof Error ? error_.message : 'Export failed.');
    } finally {
      setIsExporting(false);
    }
  }

  const totalPages = data?.total_pages ?? 0;
  const items = data?.items ?? [];

  return (
    <section aria-labelledby='admin-users-heading' className='flex flex-col gap-4'>
      <div className='flex items-center justify-between gap-4'>
        <h2 id='admin-users-heading' className='text-foreground text-lg font-semibold'>
          All users
        </h2>
        <Button
          variant='outline'
          size='sm'
          onClick={handleExport}
          disabled={isExporting}
          className='gap-2'
        >
          <Download className='size-4' aria-hidden='true' />
          {isExporting ? 'Exporting…' : 'Export CSV'}
        </Button>
      </div>
      {exportError ? (
        <p className='text-destructive text-sm' role='alert'>
          {exportError}
        </p>
      ) : null}

      {/* Filter bar */}
      <div className='flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end'>
        <div className='sm:max-w-xs sm:flex-1'>
          <Input
            type='search'
            value={searchInput}
            onChange={(event) => {
              setSearchInput(event.target.value);
            }}
            placeholder='Search by name or email…'
            leftIcon={<Search className='size-4' />}
            aria-label='Search users'
            size='sm'
          />
        </div>

        <Select
          value={roleFilter}
          onValueChange={resetToFirstPage((value) => {
            setRoleFilter(value as RoleFilter);
          })}
        >
          <SelectTrigger className='h-9 w-full sm:w-36' aria-label='Filter by role'>
            <SelectValue placeholder='Role' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>All roles</SelectItem>
            <SelectItem value='admin'>Admin</SelectItem>
            <SelectItem value='user'>User</SelectItem>
            <SelectItem value='guest'>Guest</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={activeFilter}
          onValueChange={resetToFirstPage((value) => {
            setActiveFilter(value as TriStateFilter);
          })}
        >
          <SelectTrigger className='h-9 w-full sm:w-36' aria-label='Filter by status'>
            <SelectValue placeholder='Status' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>Any status</SelectItem>
            <SelectItem value='true'>Active</SelectItem>
            <SelectItem value='false'>Inactive</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={verifiedFilter}
          onValueChange={resetToFirstPage((value) => {
            setVerifiedFilter(value as TriStateFilter);
          })}
        >
          <SelectTrigger className='h-9 w-full sm:w-40' aria-label='Filter by email verification'>
            <SelectValue placeholder='Verified' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>Any verification</SelectItem>
            <SelectItem value='true'>Verified</SelectItem>
            <SelectItem value='false'>Unverified</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className='border-border/50 bg-card relative overflow-x-auto rounded-xl border'>
        <table className='w-full border-collapse text-sm'>
          <caption className='sr-only'>
            Registered users, sortable and filterable. {data ? `${data.total} matching.` : ''}
          </caption>
          <thead className='bg-muted text-muted-foreground sticky top-[var(--app-header-height)] z-10 text-xs uppercase'>
            <tr>
              {SORTABLE_COLUMNS.map((column) => (
                <SortHeader
                  key={column.key}
                  column={column}
                  activeKey={sortBy}
                  dir={sortDir}
                  onSort={handleSort}
                />
              ))}
              <th scope='col' className='px-4 py-3 text-left font-medium'>
                Status
              </th>
              <th scope='col' className='px-4 py-3 text-left font-medium'>
                Verified
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((user: AdminUserRow, index) => (
              <tr
                key={user.id}
                className={cn(
                  'border-border/40 hover:bg-accent/30 border-t transition-colors',
                  index % 2 === 1 && 'bg-muted/30'
                )}
              >
                <td className='px-4 py-3'>
                  <div className='flex flex-col'>
                    <span className='text-foreground font-medium'>{user.full_name}</span>
                    <span className='text-muted-foreground text-xs'>@{user.username}</span>
                  </div>
                </td>
                <td className='text-muted-foreground px-4 py-3'>{user.email}</td>
                <td className='px-4 py-3'>
                  <Badge variant={ROLE_VARIANT[user.role]}>{user.role}</Badge>
                </td>
                <td className='text-muted-foreground px-4 py-3 whitespace-nowrap'>
                  {user.last_login_at ? formatRelativeTime(user.last_login_at) : 'Never'}
                </td>
                <td className='text-muted-foreground px-4 py-3 whitespace-nowrap'>
                  {formatDate(user.created_at)}
                </td>
                <td className='px-4 py-3'>
                  <StatusBadge ok={user.is_active} yes='Active' no='Inactive' />
                </td>
                <td className='px-4 py-3'>
                  <StatusBadge ok={user.is_email_verified} yes='Verified' no='Unverified' />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Empty state */}
        {!isLoading && items.length === 0 && !isError ? (
          <div className='text-muted-foreground flex flex-col items-center gap-2 py-16 text-center'>
            <Inbox className='size-8 opacity-60' aria-hidden='true' />
            <p className='text-sm'>No users match these filters.</p>
          </div>
        ) : null}

        {/* Error state */}
        {isError ? (
          <div className='text-destructive flex flex-col items-center gap-2 py-16 text-center'>
            <AlertCircle className='size-8' aria-hidden='true' />
            <p className='text-sm'>
              {error instanceof Error ? error.message : 'Failed to load users.'}
            </p>
          </div>
        ) : null}

        {/* Initial loading overlay */}
        {isLoading ? (
          <div className='flex items-center justify-center py-16'>
            <LoadingSpinner message='Loading users…' />
          </div>
        ) : null}

        {/* Background refetch indicator */}
        {!isLoading && isFetching ? (
          <div className='absolute top-2 right-2'>
            <LoadingSpinner size='sm' />
          </div>
        ) : null}
      </div>

      {/* Pagination */}
      {totalPages > 1 ? (
        <div className='flex items-center justify-between gap-4'>
          <span className='text-muted-foreground text-sm tabular-nums'>
            {data ? `${data.total.toLocaleString()} users` : ''}
          </span>
          <Pagination className='mx-0 w-auto justify-end'>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => {
                    setPage((previous) => Math.max(1, previous - 1));
                  }}
                  disabled={page <= 1}
                />
              </PaginationItem>
              {pageWindow(page, totalPages).map((entry) =>
                entry === 'ellipsis-left' || entry === 'ellipsis-right' ? (
                  <PaginationItem key={entry}>
                    <PaginationEllipsis />
                  </PaginationItem>
                ) : (
                  <PaginationItem key={entry}>
                    <PaginationButton
                      isActive={entry === page}
                      onClick={() => {
                        setPage(entry);
                      }}
                    >
                      {entry}
                    </PaginationButton>
                  </PaginationItem>
                )
              )}
              <PaginationItem>
                <PaginationNext
                  onClick={() => {
                    setPage((previous) => Math.min(totalPages, previous + 1));
                  }}
                  disabled={page >= totalPages}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      ) : null}
    </section>
  );
}
