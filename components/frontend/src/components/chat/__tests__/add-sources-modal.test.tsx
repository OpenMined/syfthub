import type { Collective } from '@/lib/collectives-api';
import type { ChatSource } from '@/lib/types';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AddSourcesModal } from '@/components/chat/add-sources-modal';
import { createMockChatSource } from '@/test/mocks/fixtures';

// ============================================================================
// Module mocks
// ============================================================================

// framer-motion: replace with pass-through elements (no animations)
vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

// OnboardingCallout: render children only (no Zustand store needed in tests)
vi.mock('@/components/onboarding', () => ({
  OnboardingCallout: ({ children }: { children: React.ReactNode }) => <>{children}</>
}));

// endpoint-utils: mock server-side search so tests are deterministic
const { mockGetPublicEndpointsPaginated } = vi.hoisted(() => ({
  mockGetPublicEndpointsPaginated: vi.fn()
}));

vi.mock('@/lib/endpoint-utils', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/endpoint-utils')>();
  type OriginalFn = typeof original.getPublicEndpointsPaginated;
  return {
    ...original,
    getPublicEndpointsPaginated: (...args: Parameters<OriginalFn>): ReturnType<OriginalFn> =>
      (mockGetPublicEndpointsPaginated as OriginalFn)(...args)
  };
});

// ============================================================================
// Test helpers / factories
// ============================================================================

function createMockCollective(overrides: Partial<Collective> = {}): Collective {
  return {
    id: 1,
    owner_id: 10,
    name: 'Test Collective',
    slug: 'test-collective',
    shared_endpoint_path: 'collective/test-collective',
    description: 'A test collective',
    about: '',
    auto_approve: false,
    icon_url: null,
    tags: ['ml'],
    verified: false,
    member_count: 3,
    owner_count: 2,
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-02T00:00:00.000Z',
    ...overrides
  };
}

/** Default props satisfying all required AddSourcesModal props. */
function defaultProps(overrides: Partial<React.ComponentProps<typeof AddSourcesModal>> = {}) {
  return {
    isOpen: true,
    onClose: vi.fn(),
    availableSources: [] as ChatSource[],
    selectedSourceIds: new Set<string>(),
    onConfirm: vi.fn(),
    ...overrides
  };
}

function renderModal(props: ReturnType<typeof defaultProps>) {
  return render(<AddSourcesModal {...props} />, {
    wrapper: ({ children }) => <MemoryRouter>{children}</MemoryRouter>
  });
}

/**
 * Find the first button with aria-pressed in the current document.
 * CollectiveItem renders one aria-pressed button (the checkbox toggle) per item.
 */
function getCheckboxButtons() {
  return screen.getAllByRole('button').filter((btn) => btn.hasAttribute('aria-pressed'));
}

// ============================================================================
// Tests
// ============================================================================

describe('AddSourcesModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: search returns empty so the endpoint-search path does not interfere
    mockGetPublicEndpointsPaginated.mockResolvedValue({ items: [] });
  });

  // --------------------------------------------------------------------------
  // Tab switcher visibility
  // --------------------------------------------------------------------------

  describe('tab switcher', () => {
    it('is hidden when availableCollectives is empty (default)', () => {
      renderModal(defaultProps());

      expect(screen.queryByRole('button', { name: /data sources/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /collectives/i })).not.toBeInTheDocument();
    });

    it('is hidden when availableCollectives is explicitly []', () => {
      renderModal(defaultProps({ availableCollectives: [] }));

      expect(screen.queryByRole('button', { name: /data sources/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /collectives/i })).not.toBeInTheDocument();
    });

    it('is shown when at least one collective is provided', () => {
      renderModal(defaultProps({ availableCollectives: [createMockCollective()] }));

      expect(screen.getByRole('button', { name: /data sources/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /collectives/i })).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // Collectives tab: content rendering
  // --------------------------------------------------------------------------

  describe('collectives tab content', () => {
    it('shows collectives after switching to the Collectives tab', async () => {
      const user = userEvent.setup();
      const collective = createMockCollective({ name: 'ML Research', slug: 'ml-research' });
      renderModal(defaultProps({ availableCollectives: [collective] }));

      await user.click(screen.getByRole('button', { name: /collectives/i }));

      expect(screen.getByText('ML Research')).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // Collectives tab: local filter (uses fireEvent + waitFor to cover the 300ms debounce)
  // --------------------------------------------------------------------------

  describe('collectives tab filtering', () => {
    it('filters collectives by name', async () => {
      const user = userEvent.setup();
      const collectives = [
        createMockCollective({
          name: 'ML Research',
          slug: 'ml-research',
          tags: ['machine-learning']
        }),
        createMockCollective({
          id: 2,
          name: 'Climate Data',
          slug: 'climate-data',
          tags: ['climate']
        })
      ];
      renderModal(defaultProps({ availableCollectives: collectives }));

      // Switch to Collectives tab
      await user.click(screen.getByRole('button', { name: /collectives/i }));

      // Use fireEvent.change to set the search value synchronously, then
      // waitFor the 300ms debounce to fire and the filter to be applied.
      const searchInput = screen.getByPlaceholderText(/search collectives/i);
      fireEvent.change(searchInput, { target: { value: 'ML' } });

      // After 300ms debounce, "Climate Data" should be filtered out
      await waitFor(() => {
        expect(screen.queryByText('Climate Data')).not.toBeInTheDocument();
      });
      expect(screen.getByText('ML Research')).toBeInTheDocument();
    });

    it('shows both collectives before any filter is applied', async () => {
      const user = userEvent.setup();
      const collectives = [
        createMockCollective({
          name: 'ML Research',
          slug: 'ml-research',
          tags: ['machine-learning']
        }),
        createMockCollective({
          id: 2,
          name: 'Climate Data',
          slug: 'climate-data',
          tags: ['climate']
        })
      ];
      renderModal(defaultProps({ availableCollectives: collectives }));

      await user.click(screen.getByRole('button', { name: /collectives/i }));

      expect(screen.getByText('ML Research')).toBeInTheDocument();
      expect(screen.getByText('Climate Data')).toBeInTheDocument();
    });

    it('filters collectives by description', async () => {
      const user = userEvent.setup();
      const collectives = [
        createMockCollective({
          name: 'Alpha',
          slug: 'alpha',
          description: 'machine learning hub'
        }),
        createMockCollective({
          id: 2,
          name: 'Beta',
          slug: 'beta',
          description: 'climate and environment'
        })
      ];
      renderModal(defaultProps({ availableCollectives: collectives }));

      await user.click(screen.getByRole('button', { name: /collectives/i }));

      const searchInput = screen.getByPlaceholderText(/search collectives/i);
      fireEvent.change(searchInput, { target: { value: 'climate' } });

      await waitFor(() => {
        expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
      });
      expect(screen.getByText('Beta')).toBeInTheDocument();
    });

    it('filters collectives by slug', async () => {
      const user = userEvent.setup();
      const collectives = [
        createMockCollective({ name: 'Alpha', slug: 'alpha-unique' }),
        createMockCollective({ id: 2, name: 'Beta', slug: 'beta-other' })
      ];
      renderModal(defaultProps({ availableCollectives: collectives }));

      await user.click(screen.getByRole('button', { name: /collectives/i }));

      const searchInput = screen.getByPlaceholderText(/search collectives/i);
      fireEvent.change(searchInput, { target: { value: 'alpha-unique' } });

      await waitFor(() => {
        expect(screen.queryByText('Beta')).not.toBeInTheDocument();
      });
      expect(screen.getByText('Alpha')).toBeInTheDocument();
    });

    it('shows empty state when no collectives match the search', async () => {
      const user = userEvent.setup();
      const collectives = [createMockCollective({ name: 'ML Research', slug: 'ml-research' })];
      renderModal(defaultProps({ availableCollectives: collectives }));

      await user.click(screen.getByRole('button', { name: /collectives/i }));

      const searchInput = screen.getByPlaceholderText(/search collectives/i);
      fireEvent.change(searchInput, { target: { value: 'zzz-no-match' } });

      await waitFor(() => {
        expect(screen.queryByText('ML Research')).not.toBeInTheDocument();
      });
      expect(screen.getByText(/no matching collectives found/i)).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // Collective selection → onConfirm payload
  // --------------------------------------------------------------------------

  describe('collective selection and confirm', () => {
    it('calls onConfirm with a source whose full_path equals the collective shared_endpoint_path', async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      const collective = createMockCollective({
        name: 'My Collective',
        slug: 'my-coll',
        shared_endpoint_path: 'collective/my-coll'
      });

      renderModal(defaultProps({ availableCollectives: [collective], onConfirm }));

      // Switch to Collectives tab
      await user.click(screen.getByRole('button', { name: /collectives/i }));

      // Click the collective item's checkbox button (the one with aria-pressed)
      const [checkboxBtn] = getCheckboxButtons();
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      await user.click(checkboxBtn!);

      // Click Confirm (now labelled "Confirm 1 Source")
      await user.click(screen.getByRole('button', { name: /confirm/i }));

      expect(onConfirm).toHaveBeenCalledOnce();
      const [passedSources] = onConfirm.mock.calls[0] as [ChatSource[]];
      expect(passedSources).toHaveLength(1);
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      expect(passedSources[0]!.full_path).toBe('collective/my-coll');
    });

    it('stores the collective with id "collective:<slug>" and type "data_source"', async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      const collective = createMockCollective({
        slug: 'my-coll',
        shared_endpoint_path: 'collective/my-coll'
      });

      renderModal(defaultProps({ availableCollectives: [collective], onConfirm }));

      await user.click(screen.getByRole('button', { name: /collectives/i }));

      const [checkboxBtn] = getCheckboxButtons();
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      await user.click(checkboxBtn!);

      await user.click(screen.getByRole('button', { name: /confirm/i }));

      const [passedSources] = onConfirm.mock.calls[0] as [ChatSource[]];
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      const source = passedSources[0]!;
      expect(source.id).toBe('collective:my-coll');
      expect(source.type).toBe('data_source');
    });

    it('updates the confirm button label to show selected count', async () => {
      const user = userEvent.setup();
      const collective = createMockCollective();
      renderModal(defaultProps({ availableCollectives: [collective] }));

      // Before selection: button says "Confirm" (no count when none selected)
      expect(screen.getByRole('button', { name: /^confirm$/i })).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: /collectives/i }));

      const [checkboxBtn] = getCheckboxButtons();
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      await user.click(checkboxBtn!);

      // Button should now say "Confirm 1 Source"
      expect(screen.getByRole('button', { name: /confirm 1 source/i })).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // Data Sources tab: unaffected by collectives prop
  // --------------------------------------------------------------------------

  describe('data sources tab', () => {
    it('shows available data sources in the endpoints tab', () => {
      const sources: ChatSource[] = [
        createMockChatSource({ name: 'Dataset A', type: 'data_source' }),
        createMockChatSource({ id: 'b', name: 'Dataset B', slug: 'b', type: 'data_source' })
      ];
      renderModal(defaultProps({ availableSources: sources }));

      expect(screen.getByText('Dataset A')).toBeInTheDocument();
      expect(screen.getByText('Dataset B')).toBeInTheDocument();
    });

    it('shows empty state when no data sources available', () => {
      renderModal(defaultProps({ availableSources: [] }));

      expect(screen.getByText(/no data sources available/i)).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // Modal open/close
  // --------------------------------------------------------------------------

  describe('modal visibility', () => {
    it('renders modal content when isOpen is true', () => {
      renderModal(defaultProps({ isOpen: true }));

      expect(screen.getByText(/add sources to context/i)).toBeInTheDocument();
    });

    it('does not render modal content when isOpen is false', () => {
      renderModal(defaultProps({ isOpen: false }));

      expect(screen.queryByText(/add sources to context/i)).not.toBeInTheDocument();
    });

    it('calls onClose when Cancel is clicked', async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      renderModal(defaultProps({ onClose }));

      await user.click(screen.getByRole('button', { name: /cancel/i }));

      expect(onClose).toHaveBeenCalledOnce();
    });
  });

  // --------------------------------------------------------------------------
  // Tab state resets when modal reopens
  // --------------------------------------------------------------------------

  describe('state reset on reopen', () => {
    it('resets to the endpoints tab when the modal is reopened', async () => {
      const user = userEvent.setup();
      const collective = createMockCollective();
      const props = defaultProps({ availableCollectives: [collective] });

      const { rerender } = render(
        <MemoryRouter>
          <AddSourcesModal {...props} />
        </MemoryRouter>
      );

      // Switch to Collectives tab
      await user.click(screen.getByRole('button', { name: /collectives/i }));
      expect(screen.getByPlaceholderText(/search collectives/i)).toBeInTheDocument();

      // Close modal (isOpen → false)
      rerender(
        <MemoryRouter>
          <AddSourcesModal {...props} isOpen={false} />
        </MemoryRouter>
      );

      // Reopen modal (isOpen → true)
      rerender(
        <MemoryRouter>
          <AddSourcesModal {...props} isOpen={true} />
        </MemoryRouter>
      );

      // Should be back on the endpoints tab — placeholder resets to "Search endpoints..."
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search endpoints/i)).toBeInTheDocument();
      });
    });
  });
});
