import Filter from 'lucide-react/dist/esm/icons/filter';
import Search from 'lucide-react/dist/esm/icons/search';

import { Badge } from './ui/badge';

interface BrowseSearchBarProps {
  /** Unique id tying the visually-hidden label to the input. */
  searchId: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  /** Visually-hidden label text for the search input. */
  searchLabel: string;
  searchPlaceholder: string;
  onOpenFilters: () => void;
  /** Whether any filter is currently applied (drives the button's accent). */
  filtersActive: boolean;
  /** Count shown in the button's badge; the badge is hidden when 0. */
  activeFilterCount: number;
}

/**
 * Search input + "Filters" button row shared by every Browse tab (data
 * sources, models, collectives) so the three tabs stay visually identical.
 */
export function BrowseSearchBar({
  searchId,
  searchValue,
  onSearchChange,
  searchLabel,
  searchPlaceholder,
  onOpenFilters,
  filtersActive,
  activeFilterCount
}: Readonly<BrowseSearchBarProps>) {
  return (
    <div className='mb-8 flex gap-4'>
      <div className='relative flex-1'>
        <label htmlFor={searchId} className='sr-only'>
          {searchLabel}
        </label>
        <Search
          className='text-muted-foreground absolute top-1/2 left-3 h-5 w-5 -translate-y-1/2'
          aria-hidden='true'
        />
        <input
          id={searchId}
          type='search'
          value={searchValue}
          onChange={(e) => {
            onSearchChange(e.target.value);
          }}
          placeholder={searchPlaceholder}
          className='font-inter border-border focus:border-primary focus:ring-ring/10 w-full rounded-lg border py-3 pr-4 pl-10 transition-colors transition-shadow focus:ring-2 focus:outline-none'
        />
      </div>
      <button
        type='button'
        onClick={onOpenFilters}
        className={`font-inter flex items-center gap-2 rounded-lg border px-4 py-3 transition-colors ${
          filtersActive
            ? 'border-primary bg-primary/5 text-primary'
            : 'border-border text-muted-foreground hover:bg-muted'
        }`}
      >
        <Filter className='h-5 w-5' aria-hidden='true' />
        Filters
        {activeFilterCount > 0 && (
          <Badge variant='secondary' className='font-inter ml-1 text-xs'>
            {activeFilterCount}
          </Badge>
        )}
      </button>
    </div>
  );
}
