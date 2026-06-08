import { create } from 'zustand';
import { EventsOff, EventsOn } from '../../wailsjs/runtime/runtime';
import { parseFrontmatter } from '../lib/markdown';
import { LogStatus } from '../lib/log-status';
import { main } from '../../wailsjs/go/models';
import {
  GetStatus,
  GetEndpoints,
  GetConfig,
  GetAggregatorURL,
  ListNetworkAgents,
  Start,
  Stop,
  ReloadEndpoints,
  GetEndpointDetail,
  SaveRunnerCode,
  SaveReadme,
  GetEnvironment,
  SetEnvironment,
  DeleteEnvironment,
  UpdateEndpointOverview,
  ToggleEndpointEnabled,
  GetLogs,
  GetLogStats,
  GetLogDetail,
  DeleteLogs,
  GetManualReviews,
  ApproveManualReview,
  RejectManualReview,
  GetSentReviews,
  SetSentReviewStatus,
  SetSentReviewNote,
  DeleteSentReview,
  CreateEndpoint,
  CheckEndpointExists,
  DeleteEndpoint,
  RenameEndpoint,
  GetLibraryPackages,
  InstallLibraryPackage,
  RunEndpointSetup,
  RespondToSetupPrompt,
  RespondToSetupSelect,
  RespondToSetupConfirm,
  CancelSetup,
} from '../../wailsjs/go/main/App';

// Re-export types from models
export type StatusInfo = main.StatusInfo;
export type EndpointInfo = main.EndpointInfo;
export type ConfigInfo = main.ConfigInfo;
export type EndpointDetail = main.EndpointDetail;
export type EnvVar = main.EnvVar;
export type RequestLogEntry = main.RequestLogEntry;
export type LogQueryResult = main.LogQueryResult;
export type LogStats = main.LogStats;
export type ManualReviewEntry = main.ManualReviewEntry;
export type SentReviewEntry = main.SentReviewEntry;
export type CreateEndpointRequest = main.CreateEndpointRequest;
export type ChatRequest = main.ChatRequest;
export type LibraryPackage = main.LibraryPackage;
export type SetupStatusInfo = main.SetupStatusInfo;
export type SetupSpecInfo = main.SetupSpecInfo;
export type SetupStepInfo = main.SetupStepInfo;
export type NetworkAgentInfo = main.NetworkAgentInfo;

// ActiveChat is the discriminated union that names which conversation the
// chat surface currently renders. The live session and any sent-review can
// each be selected; the live session's state lives in useAgentWorkflow,
// reviews' state lives in the sentReviews ledger.
export type ActiveChat =
  | { kind: 'live' }
  | { kind: 'review'; reviewId: string };

// Key under which the chat sidebar's collapsed state is persisted in
// localStorage. Keeping the key here (rather than inline at the read site)
// makes it greppable and prevents accidental key drift.
const CHAT_SIDEBAR_STORAGE_KEY = 'syfthub.chat.sidebar.collapsed';

function loadChatSidebarCollapsed(): boolean {
  // Default to collapsed: only an explicit '0' (the user expanded it before)
  // keeps the sidebar open; a missing key — first run — starts collapsed.
  if (typeof window === 'undefined') return true;
  try {
    return window.localStorage.getItem(CHAT_SIDEBAR_STORAGE_KEY) !== '0';
  } catch {
    return true;
  }
}

function persistChatSidebarCollapsed(collapsed: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CHAT_SIDEBAR_STORAGE_KEY, collapsed ? '1' : '0');
  } catch {
    // localStorage may be unavailable (private mode, denied permission). The
    // in-memory state still works; the preference simply doesn't survive a
    // restart in that environment.
  }
}

// TS-only UI label set by the setupflow:complete listener. Not a Go wire value.
export const SETUP_COMPLETE_STATUS = 'Setup complete' as const;

// Re-export for backwards compatibility — canonical definition is in @/lib/utils.
export { MULTILINE_ENV_KEYS } from '@/lib/utils';

// Wire values for transient endpoint lifecycle states (must match Go RuntimeState* constants in types.go).
export const RuntimeState = {
  Installing: 'installing',
  SettingUp: 'setting_up',
  Initializing: 'initializing',
} as const;
export type RuntimeStateValue = typeof RuntimeState[keyof typeof RuntimeState];

export interface SetupFlowState {
  running: boolean;
  slug: string | null;
  status: string | null;
  error: string | null;
  prompt: SetupPromptEvent | null;
  select: SetupSelectEvent | null;
  confirm: SetupConfirmEvent | null;
}

const SETUP_FLOW_CLEARED: SetupFlowState = {
  running: false,
  slug: null,
  status: null,
  error: null,
  prompt: null,
  select: null,
  confirm: null,
};

// LoadProgress event payload — matches filemode.LoadProgressEvent in the Go SDK.
// Emitted on the 'app:load-progress' channel for every phase transition during
// endpoint load. Frontend renders a per-endpoint progress overlay so the user
// sees what's happening during multi-minute container image pulls/builds.
export type LoadPhase =
  | 'pending'
  | 'resolving_image'
  | 'pulling_image'
  | 'building_image'
  | 'verifying_image'
  | 'materializing'
  | 'starting_container'
  | 'ready'
  | 'failed';

export interface LoadProgressEvent {
  slug: string;
  name: string;
  phase: LoadPhase;
  message?: string;
  error?: string;
  index: number;
  total: number;
}

export interface LoadProgressEntry {
  slug: string;
  name: string;
  phase: LoadPhase;
  message?: string;
  error?: string;
}

export interface LoadProgressState {
  total: number;
  entries: Record<string, LoadProgressEntry>;
}

const LOAD_PROGRESS_CLEARED: LoadProgressState = {
  total: 0,
  entries: {},
};

// Setup flow event payloads (match Go structs in setup_io.go)
export interface SetupPromptEvent {
  message: string;
  secret: boolean;
  default?: string;
  placeholder?: string;
}

export interface SetupSelectOption {
  value: string;
  label: string;
}

export interface SetupSelectEvent {
  message: string;
  options: SetupSelectOption[];
}

export interface SetupConfirmEvent {
  message: string;
}


interface AppState {
  // Core data
  status: StatusInfo;
  endpoints: EndpointInfo[];
  config: ConfigInfo | null;

  // Selection
  selectedEndpointSlug: string | null;
  selectedEndpointDetail: EndpointDetail | null;

  // Editor state
  runnerCode: string;
  originalRunnerCode: string; // For detecting unsaved changes
  readmeContent: string; // Body only (without frontmatter)
  originalReadmeContent: string; // For detecting unsaved changes
  readmeFrontmatter: string; // Hidden YAML frontmatter (preserved for saving)
  envVars: EnvVar[];

  // UI state
  isInitializing: boolean; // True during initial app load
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  activeTab: 'settings' | 'code' | 'docs' | 'logs' | 'requests';
  settingsSection: 'overview' | 'environment' | 'dependencies' | 'policies' | 'skills';
  mainView: 'endpoints' | 'chat' | 'wallet';
  // activeChat selects which conversation the chat surface renders. 'live'
  // means the in-memory live agent session (AgentChatContent). 'review'
  // means a recovered transcript from a sent_reviews row, rendered by
  // ReviewChatPane. null means no chat is selected — show the empty state.
  activeChat: ActiveChat;
  // chatSidebarCollapsed persists the user's sidebar preference across
  // sessions via localStorage (read on store init, written on each setter
  // call). A boolean rather than 'collapsed' | 'expanded' string for the
  // cheap toggle ergonomics.
  chatSidebarCollapsed: boolean;
  showLibrary: boolean;

  // Logs state
  logs: RequestLogEntry[];
  logStats: LogStats | null;
  logsLoading: boolean;
  logsHasMore: boolean;
  selectedLog: RequestLogEntry | null;
  logsStatusFilter: string;

  // Manual review state — held requests read from the endpoint's policy store.
  manualReviews: ManualReviewEntry[];
  manualReviewsLoading: boolean;
  selectedReview: ManualReviewEntry | null;
  reviewsStatusFilter: string;

  // Sent-for-review state — the client's own ledger of manual-review holds it
  // submitted (cross-endpoint, identity-scoped). Distinct from manualReviews,
  // which is the endpoint owner's view of holds against an endpoint they own.
  sentReviews: SentReviewEntry[];
  sentReviewsLoading: boolean;
  selectedSentReview: SentReviewEntry | null;
  sentReviewsFilter: string;
  /** Derived view of sentReviews grouped into continuation threads. Recomputed
   *  by fetchSentReviews whenever the underlying list changes. Empty array
   *  when no reviews exist. Consumers should prefer this over hand-rolling
   *  the grouping on every render. */
  sentReviewThreads: SentReviewThread[];

  // currentIdentity is the logged-in user's identity string (username/email/
  // whatever the Go side considers canonical). Used as defence-in-depth on
  // the manual-review:resolved listener — if a payload carries an identity
  // that doesn't match, drop it. Null when not yet known (the wire event has
  // no identity today, so this is forward-compat groundwork).
  currentIdentity: string | null;

  // Create endpoint state
  isCreateDialogOpen: boolean;
  isCreatingEndpoint: boolean;

  // Delete endpoint state
  isDeleteDialogOpen: boolean;
  isDeletingEndpoint: boolean;

  // Rename endpoint state
  isRenameDialogOpen: boolean;
  isRenamingEndpoint: boolean;

  // Chat state — the agent dropdown is sourced from the hub browse list, so the
  // selected agent is a NetworkAgentInfo, not a local EndpointInfo. Data-source
  // selections still come from local endpoints.
  chatSelectedModel: NetworkAgentInfo | null;
  chatSelectedSources: EndpointInfo[];
  aggregatorURL: string | null;

  // Network agents (public agents discovered via the hub — NOT locally installed).
  // Kept separate from `endpoints` because invoking a network agent must go
  // through the hub/aggregator path, not the local runner.
  networkAgents: NetworkAgentInfo[];
  networkAgentsLoading: boolean;
  networkAgentsLastFetchedAt: number | null;

  // Library state
  libraryPackages: LibraryPackage[];
  libraryLoading: boolean;
  libraryError: string | null;
  installingPackageSlug: string | null;

  // Setup flow state
  setupFlow: SetupFlowState;

  // Endpoint-load progress (initial startup and watcher reloads). Cleared
  // when all entries terminate (ready or failed). See LoadProgress component.
  loadProgress: LoadProgressState;

  // Actions - Core
  initialize: () => Promise<void>; // Initial app load
  fetchStatus: () => Promise<void>;
  fetchEndpoints: () => Promise<void>;
  fetchConfig: () => Promise<void>;
  startService: () => Promise<void>;
  stopService: () => Promise<void>;
  reloadEndpoints: () => Promise<void>;
  dismissLoadProgress: () => void;

  // Actions - Selection
  selectEndpoint: (slug: string | null) => Promise<void>;
  setActiveTab: (tab: 'settings' | 'code' | 'docs' | 'logs' | 'requests') => void;
  setSettingsSection: (section: 'overview' | 'environment' | 'dependencies' | 'policies' | 'skills') => void;
  setMainView: (view: 'endpoints' | 'chat' | 'wallet') => void;
  // setActiveChat is the new entry point — sidebar items + continuation flow
  // both use this to switch what the chat surface renders.
  setActiveChat: (chat: ActiveChat) => void;
  setChatSidebarCollapsed: (collapsed: boolean) => void;
  setShowLibrary: (show: boolean) => void;

  // Actions - Logs
  fetchLogs: (status?: string) => Promise<void>;
  fetchLogStats: () => Promise<void>;
  loadMoreLogs: (status?: string) => Promise<void>;
  setSelectedLog: (log: RequestLogEntry | null) => void;
  setLogsStatusFilter: (status: string) => void;
  deleteLogs: () => Promise<void>;

  // Actions - Manual reviews
  fetchManualReviews: (status?: string) => Promise<void>;
  setSelectedReview: (review: ManualReviewEntry | null) => void;
  setReviewsStatusFilter: (status: string) => void;
  approveManualReview: (reviewId: string) => Promise<void>;
  rejectManualReview: (reviewId: string, reason: string) => Promise<void>;

  // Actions - Sent reviews (the client's own manual-review ledger)
  fetchSentReviews: () => Promise<void>;
  setSelectedSentReview: (review: SentReviewEntry | null) => void;
  setSentReviewsFilter: (status: string) => void;
  markSentReviewStatus: (reviewId: string, status: 'approved' | 'rejected', reason: string) => Promise<void>;
  saveSentReviewNote: (reviewId: string, note: string) => Promise<void>;
  // deleteSentReview removes the row from the local ledger (no host
  // communication). The caller is responsible for any UI consequences —
  // notably, if the currently-active chat is this review, switching
  // activeChat back to 'live' so the surface doesn't render a stale id.
  deleteSentReview: (reviewId: string) => Promise<void>;
  // applyResolvedEvent is the internal handler wired to the Go runtime event
  // 'manual-review:resolved'. Exposed on the store (rather than closed over
  // in initialize) so it's unit-testable and so re-registering the listener
  // doesn't need a fresh closure each time. Returns void; errors surface
  // through the existing error field if any reconcile fetch fails.
  applyResolvedEvent: (payload: ManualReviewResolvedPayload) => void;

  // Actions - Code
  setRunnerCode: (code: string) => void;
  saveRunnerCode: () => Promise<void>;

  // Actions - Readme
  setReadmeContent: (content: string) => void;
  saveReadme: () => Promise<void>;

  // Actions - Environment
  fetchEnvVars: () => Promise<void>;
  setEnvVar: (key: string, value: string) => Promise<void>;
  deleteEnvVar: (key: string) => Promise<void>;

  // Actions - Overview
  updateOverview: (name: string, description: string, type: string, version: string) => Promise<void>;
  toggleEnabled: () => Promise<void>;

  // Actions - Utility
  clearError: () => void;
  refreshAll: () => Promise<void>;

  // Actions - Create Endpoint
  setCreateDialogOpen: (open: boolean) => void;
  checkEndpointExists: (name: string) => Promise<{ slug: string; exists: boolean }>;
  createEndpoint: (request: {
    name: string;
    type: string;
    description?: string;
    version?: string;
  }) => Promise<string>;

  // Actions - Delete Endpoint
  setDeleteDialogOpen: (open: boolean) => void;
  deleteEndpoint: () => Promise<void>;

  // Actions - Rename Endpoint
  setRenameDialogOpen: (open: boolean) => void;
  renameEndpoint: (newName: string) => Promise<string>;

  // Actions - Chat
  setChatSelectedModel: (model: NetworkAgentInfo | null) => void;
  setChatSelectedSources: (sources: EndpointInfo[]) => void;
  toggleChatSource: (source: EndpointInfo) => void;
  refreshAggregatorURL: () => Promise<void>;
  fetchNetworkAgents: (force?: boolean) => Promise<void>;

  // Actions - Library
  fetchLibraryPackages: () => Promise<void>;
  installLibraryPackage: (slug: string, downloadUrl: string, configValues?: Record<string, string>) => Promise<void>;
  uninstallLibraryPackage: (slug: string) => Promise<void>;

  // Actions - Setup flow
  runSetup: (slug: string, force?: boolean) => Promise<void>;
  respondToSetupPrompt: (value: string) => Promise<void>;
  respondToSetupSelect: (value: string) => Promise<void>;
  respondToSetupConfirm: (confirmed: boolean) => Promise<void>;
  cancelSetup: () => Promise<void>;
  clearSetupFlow: () => void;
}

const initialStatus: StatusInfo = {
  state: 'idle',
  mode: 'unknown',
  errorMessage: undefined,
  uptime: undefined,
};

let logStatsDebounceTimer: ReturnType<typeof setTimeout> | null = null;

// Trailing-edge debounce for "the sent-reviews ledger may have changed but
// the wire event didn't carry enough fields to splice in place". Mirrors the
// logStatsDebounceTimer pattern: module-level so multiple events within the
// window coalesce into a single fetchSentReviews call.
let pendingReconcileTimer: ReturnType<typeof setTimeout> | null = null;

// The shape of the payload emitted by the Go review_lifecycle.go runtime
// event "manual-review:resolved". Kept as a TS-side type because Wails does
// not generate a struct for this map[string]any literal.
//
// NOTE: the Go emit sites carry only these four fields. responseText /
// resolvedAt are NOT in the payload — they live in the Go ledger and are
// only readable via GetSentReviews. That's why this listener's splice path
// can't update an approved row in place; it must reconcile via fetch.
interface ManualReviewResolvedPayload {
  reviewId?: string;
  status?: string;
  endpointSlug?: string;
  endpointOwner?: string;
  // Defence-in-depth: not currently emitted by Go, but the store accepts it
  // if a future emit adds it, so the identity guard activates automatically.
  identity?: string;
}

// Field-tuple equality for the SentReviews list. Avoids JSON.stringify (which
// would be O(n × responseTextLength) — responseText can be very long for
// approved entries). Compares only the fields that drive what the user sees;
// other fields (endpointName, requestMessages, etc.) don't transition through
// the manual-review:resolved event, so a change to them can be ignored here.
// scheduleReconcile coalesces a burst of manual-review:resolved events into
// a single fetchSentReviews call ~250ms after the last event. Trailing-edge
// debounce — first event in a burst schedules, subsequent events reset the
// timer, the fetch runs once when the burst settles. Mirrors the existing
// logStatsDebounceTimer pattern; the function takes the store's `get` so
// the always-current filter is read when the timer fires (not when it's
// scheduled).
function scheduleReconcile(get: () => AppState): void {
  if (pendingReconcileTimer) clearTimeout(pendingReconcileTimer);
  pendingReconcileTimer = setTimeout(() => {
    pendingReconcileTimer = null;
    void get().fetchSentReviews();
  }, 250);
}

// SentReviewThread groups a chain of continuation reviews into one logical
// conversation. The sidebar shows one item per thread; the chat pane
// renders the thread's latest review (its status drives the badge, its
// transcript drives the rendering). A thread with one review (no
// continuations) is degenerate but still a thread.
export interface SentReviewThread {
  /** The root reviewId — earliest review in the chain. Stable thread key. */
  threadId: string;
  /** All reviews in chronological order (oldest first). */
  reviews: SentReviewEntry[];
  /** Most-recent review — drives sidebar badge + chat pane rendering. */
  latestReview: SentReviewEntry;
}

/** Decide whether `b` is a continuation of `a` by transcript shape. Used
 *  only as a fallback for rows that lack parentReviewId (synth rows from
 *  ApplyHostResolution on a fresh device). `b` extends `a` iff b's first
 *  N messages match a's transcript, position N is an assistant turn whose
 *  content equals a.responseText, and b has at least one more message after
 *  that (the new user turn). */
function isTranscriptContinuation(
  parent: SentReviewEntry,
  child: SentReviewEntry,
): boolean {
  if (parent.endpointPath !== child.endpointPath) return false;
  if (parent.status !== 'approved') return false;
  const a = parent.requestMessages ?? [];
  const b = child.requestMessages ?? [];
  if (b.length < a.length + 2) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i].role !== b[i].role || a[i].content !== b[i].content) return false;
  }
  const bridge = b[a.length];
  if (bridge.role !== 'assistant') return false;
  if (parent.responseText && bridge.content !== parent.responseText) return false;
  return true;
}

/** Compute the thread grouping for a list of reviews.
 *
 *  Primary rule: walk `parentReviewId` links to find each review's root.
 *  Fallback: for reviews with no parent (legacy rows, or synth rows from
 *  cross-device delivery), attempt transcript-prefix matching against
 *  candidate parents. The fallback only fires when the primary rule
 *  couldn't link the row — it never overrides an explicit parent.
 *
 *  Complexity: O(n) for parent walking (with memoization), O(n²) worst
 *  case for the fallback when many rows lack parentReviewId. At
 *  maxSentReviewRows=1000 this is acceptable; we can index by endpointPath
 *  if it ever becomes hot. */
export function computeSentReviewThreads(reviews: SentReviewEntry[]): SentReviewThread[] {
  if (reviews.length === 0) return [];

  const byId = new Map<string, SentReviewEntry>();
  for (const r of reviews) byId.set(r.reviewId, r);

  // Resolve effective parents: explicit parentReviewId wins; otherwise try
  // transcript-prefix matching against any prior review. The "newest viable
  // parent" wins the tie if multiple candidates match (most recent context
  // is most likely what the user was looking at).
  const effectiveParent = new Map<string, string>();
  // Iterate chronologically so a transcript-fallback lookup only sees
  // reviews that existed when this one was captured.
  const chrono = [...reviews].sort(
    (a, b) => a.submittedAt.localeCompare(b.submittedAt),
  );
  for (let i = 0; i < chrono.length; i++) {
    const r = chrono[i];
    if (r.parentReviewId && byId.has(r.parentReviewId)) {
      effectiveParent.set(r.reviewId, r.parentReviewId);
      continue;
    }
    // Fallback only — scan earlier rows for a transcript-prefix match.
    let bestParent: SentReviewEntry | null = null;
    for (let j = i - 1; j >= 0; j--) {
      const candidate = chrono[j];
      if (isTranscriptContinuation(candidate, r)) {
        if (
          !bestParent ||
          (candidate.requestMessages?.length ?? 0) > (bestParent.requestMessages?.length ?? 0)
        ) {
          bestParent = candidate;
        }
      }
    }
    if (bestParent) effectiveParent.set(r.reviewId, bestParent.reviewId);
  }

  // Resolve each review's root by walking the effective-parent map.
  const rootCache = new Map<string, string>();
  function findRoot(id: string, seen = new Set<string>()): string {
    const cached = rootCache.get(id);
    if (cached !== undefined) return cached;
    if (seen.has(id)) {
      // Cycle guard. parentReviewId is set on write and never updated, so
      // a cycle is impossible in practice — but the cost of guarding is one
      // Set, and the cost of NOT guarding is a stack overflow.
      rootCache.set(id, id);
      return id;
    }
    seen.add(id);
    const parent = effectiveParent.get(id);
    if (!parent || !byId.has(parent)) {
      rootCache.set(id, id);
      return id;
    }
    const root = findRoot(parent, seen);
    rootCache.set(id, root);
    return root;
  }

  const groups = new Map<string, SentReviewEntry[]>();
  for (const r of reviews) {
    const root = findRoot(r.reviewId);
    const bucket = groups.get(root) ?? [];
    bucket.push(r);
    groups.set(root, bucket);
  }

  const threads: SentReviewThread[] = [];
  for (const [threadId, members] of groups) {
    members.sort((a, b) => a.submittedAt.localeCompare(b.submittedAt));
    threads.push({
      threadId,
      reviews: members,
      latestReview: members[members.length - 1],
    });
  }
  // Sidebar reads this in order; newest activity first.
  threads.sort(
    (a, b) => b.latestReview.submittedAt.localeCompare(a.latestReview.submittedAt),
  );
  return threads;
}

function sentReviewsEqual(a: SentReviewEntry[], b: SentReviewEntry[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (
      x.reviewId !== y.reviewId ||
      x.status !== y.status ||
      x.submittedAt !== y.submittedAt ||
      x.userNote !== y.userNote ||
      x.resolvedAt !== y.resolvedAt ||
      x.responseText !== y.responseText ||
      x.parentReviewId !== y.parentReviewId
    ) {
      return false;
    }
  }
  return true;
}

function endpointsEqual(a: EndpointInfo[], b: EndpointInfo[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (
      x.slug !== y.slug ||
      x.name !== y.name ||
      x.type !== y.type ||
      x.enabled !== y.enabled ||
      x.version !== y.version ||
      x.hasPolicies !== y.hasPolicies ||
      x.runtimeState !== y.runtimeState
    ) {
      return false;
    }
  }
  return true;
}

function networkAgentsEqual(a: NetworkAgentInfo[], b: NetworkAgentInfo[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (
      x.slug !== y.slug ||
      x.ownerUsername !== y.ownerUsername ||
      x.name !== y.name ||
      x.version !== y.version ||
      x.starsCount !== y.starsCount ||
      x.updatedAt !== y.updatedAt
    ) {
      return false;
    }
  }
  return true;
}

/** Build the state patch that removes `slug` from endpoint-related selections.
 * Note: chatSelectedModel is intentionally not touched here — it now points at
 * a hub-discovered NetworkAgentInfo, not a local endpoint.
 */
function removedSlugPatch(
  state: Pick<AppState, 'endpoints' | 'chatSelectedSources'>,
  slug: string,
): Pick<AppState, 'endpoints' | 'chatSelectedSources'> {
  return {
    endpoints: state.endpoints.filter(ep => ep.slug !== slug),
    chatSelectedSources: state.chatSelectedSources.filter(ep => ep.slug !== slug),
  };
}

export const useAppStore = create<AppState>((set, get) => ({
  // Initial state
  status: initialStatus,
  endpoints: [],
  config: null,
  selectedEndpointSlug: null,
  selectedEndpointDetail: null,
  runnerCode: '',
  originalRunnerCode: '',
  readmeContent: '',
  originalReadmeContent: '',
  readmeFrontmatter: '',
  envVars: [],
  isInitializing: true, // Start as true, will be set to false after initialize()
  isLoading: false,
  isSaving: false,
  error: null,
  activeTab: 'settings',
  settingsSection: 'overview',
  mainView: 'chat',
  activeChat: { kind: 'live' },
  chatSidebarCollapsed: loadChatSidebarCollapsed(),
  showLibrary: false,

  // Logs initial state
  logs: [],
  logStats: null,
  logsLoading: false,
  logsHasMore: false,
  selectedLog: null,
  logsStatusFilter: 'all',

  // Manual review initial state
  manualReviews: [],
  manualReviewsLoading: false,
  selectedReview: null,
  reviewsStatusFilter: 'pending',

  // Sent review initial state
  sentReviews: [],
  sentReviewThreads: [],
  sentReviewsLoading: false,
  selectedSentReview: null,
  sentReviewsFilter: 'pending',
  currentIdentity: null,

  // Create endpoint initial state
  isCreateDialogOpen: false,
  isCreatingEndpoint: false,

  // Delete endpoint initial state
  isDeleteDialogOpen: false,
  isDeletingEndpoint: false,

  // Rename endpoint initial state
  isRenameDialogOpen: false,
  isRenamingEndpoint: false,

  // Chat initial state
  chatSelectedModel: null,
  chatSelectedSources: [],
  aggregatorURL: null,
  networkAgents: [],
  networkAgentsLoading: false,
  networkAgentsLastFetchedAt: null,

  // Library initial state
  libraryPackages: [],
  libraryLoading: false,
  libraryError: null,
  installingPackageSlug: null,

  // Setup flow initial state
  setupFlow: { ...SETUP_FLOW_CLEARED },

  // Load progress initial state
  loadProgress: { ...LOAD_PROGRESS_CLEARED },

  // Core actions
  initialize: async () => {
    try {
      set({ isInitializing: true, error: null });

      // Wait for config to be ready (backend emits this after initSyftClient)
      const config = await new Promise<any>((resolve, reject) => {
        const timeout = setTimeout(() => {
          cleanup();
          reject(new Error('Configuration incomplete - SpaceURL not set. Check your API key and connection.'));
        }, 10000); // 10s timeout as fallback

        const cleanup = EventsOn('app:config-ready', () => {
          clearTimeout(timeout);
          cleanup();
          resolve(GetConfig());
        });

        // Also try immediately in case the event already fired
        GetConfig().then(c => {
          if (c.spaceUrl) {
            clearTimeout(timeout);
            cleanup();
            resolve(c);
          }
        });
      });

      // Register the load-progress listener BEFORE Start() — Setup() runs
      // synchronously inside Start() and emits every pending → ready event
      // before Start() returns. Registering later (with the other listeners
      // below) misses them all. EventsOff first so re-running initialize()
      // doesn't stack handlers.
      EventsOff('app:load-progress');
      EventsOn('app:load-progress', (ev: LoadProgressEvent) => {
        set(s => {
          const prev = s.loadProgress.entries[ev.slug];
          if (prev
            && prev.phase === ev.phase
            && prev.message === ev.message
            && prev.error === ev.error
            && ev.total <= s.loadProgress.total) {
            return s;
          }
          const entry: LoadProgressEntry = {
            slug: ev.slug,
            name: ev.name,
            phase: ev.phase,
            message: ev.message,
            error: ev.error,
          };
          const entries = { ...s.loadProgress.entries, [ev.slug]: entry };
          let allTerminal = true;
          let hadFailure = false;
          for (const e of Object.values(entries)) {
            if (e.phase === 'failed') hadFailure = true;
            else if (e.phase !== 'ready') { allTerminal = false; break; }
          }
          if (allTerminal && !hadFailure) {
            return { loadProgress: { ...LOAD_PROGRESS_CLEARED } };
          }
          return {
            loadProgress: {
              total: ev.total > s.loadProgress.total ? ev.total : s.loadProgress.total,
              entries,
            },
          };
        });
      });

      // Start the service (required before reloading endpoints)
      await Start();

      // Poll until the service state is 'running' (max 10 seconds)
      const maxAttempts = 50;
      let attempts = 0;
      while (attempts < maxAttempts) {
        const status = await GetStatus();
        if (status.state === 'running') {
          break;
        }
        if (status.state === 'error') {
          throw new Error(status.errorMessage || 'Service failed to start');
        }
        await new Promise(resolve => setTimeout(resolve, 200));
        attempts++;
      }

      if (attempts >= maxAttempts) {
        throw new Error('Timeout waiting for service to start');
      }

      // Fetch all data including aggregator URL
      // Note: no ReloadEndpoints() here — Setup() already loaded all endpoints
      // during Start(). Calling it here would stop and recreate all containers
      // unnecessarily (10s+ docker stop grace period per container).
      await Promise.all([
        get().fetchStatus(),
        get().fetchEndpoints(),
        get().fetchConfig(),
        get().refreshAggregatorURL(),
        get().fetchNetworkAgents(),
        // Initial sent-reviews load, moved out of the components. Always
        // fetches the full list (see fetchSentReviews rationale); the view
        // layer narrows by sentReviewsFilter.
        get().fetchSentReviews(),
      ]);

      // Deregister any previous listeners before re-registering so multiple
      // initialize() calls (e.g. reconnect, re-login) don't stack handlers.
      EventsOff(
        'app:config-ready',
        'app:endpoints-changed',
        'app:new-log',
        'manual-review:resolved',
        'setupflow:started',
        'setupflow:prompt',
        'setupflow:select',
        'setupflow:confirm',
        'setupflow:status',
        'setupflow:error',
        'setupflow:complete',
        'setupflow:failed',
      );

      {
        // Refetch the hub agent list whenever auth state changes. The backend
        // emits app:config-ready every time initSyftClient runs — at boot, on
        // first login, and on any settings update — so this catches the case
        // where the initial fetch ran with syftClient still nil.
        EventsOn('app:config-ready', () => {
          // force: auth identity may have changed, so bypass the TTL.
          void get().fetchNetworkAgents(true);
        });

        // The file watcher is the ground truth. When it fires, the emitted list
        // is exactly what exists on disk — replace state unconditionally.
        EventsOn('app:endpoints-changed', (incomingEndpoints: EndpointInfo[]) => {
          const agentOnly = (incomingEndpoints || []).filter((ep: EndpointInfo) => ep.type === 'agent');

          if (endpointsEqual(get().endpoints, agentOnly)) return;

          const slugSet = new Set(agentOnly.map(ep => ep.slug));
          const { chatSelectedSources } = get();
          set({
            endpoints: agentOnly,
            chatSelectedSources: chatSelectedSources.filter(ep => slugSet.has(ep.slug)),
          });
        });

        // Listen for setup flow events
        // The Go backend emits setupflow:started synchronously before the goroutine,
        // so it arrives before any step events.
        EventsOn('setupflow:started', (slug: string) => {
          set({ setupFlow: { ...SETUP_FLOW_CLEARED, running: true, slug, status: 'Starting setup...' } });
        });
        // Each interactive event also ensures running is true,
        // in case the goroutine fires before the frontend sets state.
        EventsOn('setupflow:prompt', (event: SetupPromptEvent) => {
          set(s => ({ setupFlow: { ...s.setupFlow, running: true, prompt: event, select: null, confirm: null } }));
        });
        EventsOn('setupflow:select', (event: SetupSelectEvent) => {
          set(s => ({ setupFlow: { ...s.setupFlow, running: true, select: event, prompt: null, confirm: null } }));
        });
        EventsOn('setupflow:confirm', (event: SetupConfirmEvent) => {
          set(s => ({ setupFlow: { ...s.setupFlow, running: true, confirm: event, prompt: null, select: null } }));
        });
        EventsOn('setupflow:status', (message: string) => {
          set(s => ({ setupFlow: { ...s.setupFlow, running: true, status: message } }));
        });
        EventsOn('setupflow:error', (message: string) => {
          set(s => ({ setupFlow: { ...s.setupFlow, error: message } }));
        });
        EventsOn('setupflow:complete', () => {
          set({ setupFlow: { ...SETUP_FLOW_CLEARED, status: SETUP_COMPLETE_STATUS } });
          // app:endpoints-changed fires immediately after this event (from the same goroutine),
          // carrying the already-updated endpoint list — no separate fetchEndpoints() needed.
        });
        EventsOn('setupflow:failed', (errorMsg: string) => {
          set({ setupFlow: { ...SETUP_FLOW_CLEARED, error: errorMsg } });
        });

        // Centralised subscription for host-delivered manual-review
        // resolutions. The Go ReviewInboxListener emits one of these after
        // every successful Apply. Routing through the store (rather than
        // each view subscribing on its own) avoids duplicate listeners,
        // gives StrictMode-safe cleanup via the EventsOff above, and lets
        // the splice/reconcile logic live in one place.
        EventsOn('manual-review:resolved', (payload: ManualReviewResolvedPayload) => {
          useAppStore.getState().applyResolvedEvent(payload);
        });

        // Listen for new log events (real-time log updates). Agent sessions
        // emit multiple snapshots with the same id — a "running" snapshot at
        // session start and on every ~1.5s ticker, followed by a single
        // terminal snapshot. We upsert by id so the running row updates in
        // place and finalizes when the terminal entry arrives.
        EventsOn('app:new-log', (entry: RequestLogEntry) => {
          const { selectedEndpointSlug, logs } = get();
          if (entry.endpointSlug !== selectedEndpointSlug) return;

          const idx = logs.findIndex(l => l.id === entry.id);
          let next: RequestLogEntry[];
          if (idx >= 0) {
            next = logs.slice();
            next[idx] = entry;
          } else if (logs.length < 200) {
            next = [entry, ...logs];
          } else {
            next = [entry, ...logs.slice(0, 199)];
          }
          set({ logs: next });

          // Running snapshots don't change the persisted stats — only refresh
          // on terminal entries so an active token-streaming session doesn't
          // trigger IPC every 1.5s.
          if (entry.status !== LogStatus.Running) {
            if (logStatsDebounceTimer) clearTimeout(logStatsDebounceTimer);
            logStatsDebounceTimer = setTimeout(() => { get().fetchLogStats(); }, 2000);
          }
        });
      }
    } catch (err) {
      set({ error: `Failed to initialize: ${err}` });
    } finally {
      set({ isInitializing: false });
    }
  },

  fetchStatus: async () => {
    try {
      const status = await GetStatus();
      set({ status });
    } catch (err) {
      set({ error: `Failed to fetch status: ${err}` });
    }
  },

  fetchEndpoints: async () => {
    try {
      const allEndpoints = await GetEndpoints();
      const endpoints = allEndpoints.filter((ep: EndpointInfo) => ep.type === 'agent');
      set({ endpoints });
    } catch (err) {
      set({ error: `Failed to fetch endpoints: ${err}` });
    }
  },

  fetchConfig: async () => {
    try {
      const config = await GetConfig();
      set({ config });
    } catch (err) {
      set({ error: `Failed to fetch config: ${err}` });
    }
  },

  startService: async () => {
    try {
      set({ isLoading: true, error: null });
      await Start();
      // Wait for the backend's app:state-changed event instead of a fixed sleep.
      await new Promise<void>((resolve) => {
        const cancel = EventsOn('app:state-changed', (s: StatusInfo) => {
          if (s.state === 'running' || s.state === 'error') { cancel(); resolve(); }
        });
        setTimeout(() => { cancel(); resolve(); }, 10000);
      });
      await get().fetchStatus();
    } catch (err) {
      set({ error: `Failed to start service: ${err}` });
    } finally {
      set({ isLoading: false });
    }
  },

  stopService: async () => {
    try {
      set({ isLoading: true, error: null });
      await Stop();
      // Wait for the backend's app:state-changed event instead of a fixed sleep.
      await new Promise<void>((resolve) => {
        const cancel = EventsOn('app:state-changed', (s: StatusInfo) => {
          if (s.state === 'idle' || s.state === 'error') { cancel(); resolve(); }
        });
        setTimeout(() => { cancel(); resolve(); }, 15000);
      });
      await get().fetchStatus();
    } catch (err) {
      set({ error: `Failed to stop service: ${err}` });
    } finally {
      set({ isLoading: false });
    }
  },

  reloadEndpoints: async () => {
    try {
      set({ isLoading: true, error: null });
      await ReloadEndpoints();
      await get().fetchEndpoints();
    } catch (err) {
      set({ error: `Failed to reload endpoints: ${err}` });
    } finally {
      set({ isLoading: false });
    }
  },

  dismissLoadProgress: () => {
    set({ loadProgress: { ...LOAD_PROGRESS_CLEARED } });
  },

  // Selection actions
  selectEndpoint: async (slug: string | null) => {
    if (!slug) {
      set({
        selectedEndpointSlug: null,
        selectedEndpointDetail: null,
        runnerCode: '',
        originalRunnerCode: '',
        readmeContent: '',
        originalReadmeContent: '',
        readmeFrontmatter: '',
        envVars: [],
        // Clear logs state
        logs: [],
        logStats: null,
        logsHasMore: false,
        selectedLog: null,
        // Clear manual review state
        manualReviews: [],
        selectedReview: null,
      });
      return;
    }

    try {
      set({ isLoading: true, error: null, showLibrary: false });

      // Fetch endpoint detail - includes runnerCode and readmeContent
      const detail = await GetEndpointDetail(slug);

      // Fetch env vars
      let envVars: EnvVar[] = [];
      try {
        envVars = await GetEnvironment(slug) || [];
      } catch {
        // Env file might not exist
      }

      const code = detail.runnerCode || '';
      const fullReadme = detail.readmeContent || '';
      // Parse frontmatter from readme - only show body in editor
      const { frontmatter, body } = parseFrontmatter(fullReadme);
      set({
        selectedEndpointSlug: slug,
        selectedEndpointDetail: detail,
        runnerCode: code,
        originalRunnerCode: code,
        readmeContent: body,
        originalReadmeContent: body,
        readmeFrontmatter: frontmatter,
        envVars,
        activeTab: 'settings' as const,
        settingsSection: 'overview' as const,
        // Reset logs state for new endpoint
        logs: [],
        logStats: null,
        logsHasMore: false,
        selectedLog: null,
        logsStatusFilter: 'all',
        // Reset manual review state for new endpoint
        manualReviews: [],
        selectedReview: null,
        reviewsStatusFilter: 'pending',
      });
    } catch (err) {
      set({ error: `Failed to load endpoint: ${err}` });
    } finally {
      set({ isLoading: false });
    }
  },

  setActiveTab: (tab) => {
    set({ activeTab: tab });
  },

  setSettingsSection: (section) => {
    set({ settingsSection: section });
  },

  setMainView: (view) => {
    set({ mainView: view, showLibrary: false });
  },

  setActiveChat: (chat) => {
    // Mirror the chat selection into selectedSentReview when a review is
    // chosen so existing detail-panel readers (the old SentReviewsView still
    // mounted as a fallback) stay coherent. Cheap; no extra fetch.
    if (chat.kind === 'review') {
      const review = get().sentReviews.find((r) => r.reviewId === chat.reviewId) ?? null;
      set({ activeChat: chat, selectedSentReview: review });
    } else {
      set({ activeChat: chat, selectedSentReview: null });
    }
  },

  setChatSidebarCollapsed: (collapsed) => {
    persistChatSidebarCollapsed(collapsed);
    set({ chatSidebarCollapsed: collapsed });
  },

  setShowLibrary: (show) => {
    if (show) {
      set({ showLibrary: true, selectedEndpointSlug: null, selectedEndpointDetail: null });
    } else {
      set({ showLibrary: false });
    }
  },

  // Code actions
  setRunnerCode: (code: string) => {
    set({ runnerCode: code });
  },

  saveRunnerCode: async () => {
    const { selectedEndpointSlug, runnerCode } = get();
    if (!selectedEndpointSlug) return;

    try {
      set({ isSaving: true, error: null });
      await SaveRunnerCode(selectedEndpointSlug, runnerCode);
      // Update original to match saved content (resets dirty state)
      set({ originalRunnerCode: runnerCode });
    } catch (err) {
      set({ error: `Failed to save code: ${err}` });
      throw err;
    } finally {
      set({ isSaving: false });
    }
  },

  // Readme actions
  setReadmeContent: (content: string) => {
    set({ readmeContent: content });
  },

  saveReadme: async () => {
    const { selectedEndpointSlug, readmeContent, readmeFrontmatter } = get();
    if (!selectedEndpointSlug) return;

    try {
      set({ isSaving: true, error: null });
      // Combine frontmatter with body for saving
      const fullContent = readmeFrontmatter
        ? `${readmeFrontmatter}\n\n${readmeContent}`
        : readmeContent;
      await SaveReadme(selectedEndpointSlug, fullContent);
      // Update the detail to reflect readme exists
      const detail = get().selectedEndpointDetail;
      if (detail) {
        set({ selectedEndpointDetail: main.EndpointDetail.createFrom({ ...detail, hasReadme: true }) });
      }
      // Update original to match saved content (resets dirty state)
      set({ originalReadmeContent: readmeContent });
    } catch (err) {
      set({ error: `Failed to save readme: ${err}` });
      throw err;
    } finally {
      set({ isSaving: false });
    }
  },

  // Environment actions
  fetchEnvVars: async () => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;

    try {
      const envVars = await GetEnvironment(selectedEndpointSlug) || [];
      set({ envVars });
    } catch (err) {
      set({ envVars: [] });
    }
  },

  setEnvVar: async (key: string, value: string) => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;

    try {
      set({ isSaving: true, error: null });
      await SetEnvironment(selectedEndpointSlug, key, value);
      await get().fetchEnvVars();
    } catch (err) {
      set({ error: `Failed to set environment variable: ${err}` });
      throw err;
    } finally {
      set({ isSaving: false });
    }
  },

  deleteEnvVar: async (key: string) => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;

    try {
      set({ isSaving: true, error: null });
      await DeleteEnvironment(selectedEndpointSlug, key);
      await get().fetchEnvVars();
    } catch (err) {
      set({ error: `Failed to delete environment variable: ${err}` });
      throw err;
    } finally {
      set({ isSaving: false });
    }
  },

  // Overview actions
  updateOverview: async (name: string, description: string, type: string, version: string) => {
    const { selectedEndpointSlug, selectedEndpointDetail } = get();
    if (!selectedEndpointSlug || !selectedEndpointDetail) return;

    try {
      set({ isSaving: true, error: null });
      await UpdateEndpointOverview(selectedEndpointSlug, name, description, type, version);
      // Update local state
      set({
        selectedEndpointDetail: main.EndpointDetail.createFrom({
          ...selectedEndpointDetail,
          name,
          description,
          type,
          version,
        }),
      });
      // Refresh endpoints list
      await get().fetchEndpoints();
    } catch (err) {
      set({ error: `Failed to update overview: ${err}` });
      throw err;
    } finally {
      set({ isSaving: false });
    }
  },

  toggleEnabled: async () => {
    const { selectedEndpointSlug, selectedEndpointDetail } = get();
    if (!selectedEndpointSlug || !selectedEndpointDetail) return;

    try {
      set({ isSaving: true, error: null });
      const newEnabled = await ToggleEndpointEnabled(selectedEndpointSlug);
      set({
        selectedEndpointDetail: main.EndpointDetail.createFrom({
          ...selectedEndpointDetail,
          enabled: newEnabled,
        }),
      });
      // Refresh endpoints list
      await get().fetchEndpoints();
    } catch (err) {
      set({ error: `Failed to toggle endpoint: ${err}` });
      throw err;
    } finally {
      set({ isSaving: false });
    }
  },

  // Utility actions
  clearError: () => {
    set({ error: null });
  },

  refreshAll: async () => {
    try {
      set({ isLoading: true, error: null });
      await Promise.all([
        get().fetchStatus(),
        get().fetchEndpoints(),
        get().fetchConfig(),
      ]);
    } catch (err) {
      set({ error: `Failed to refresh: ${err}` });
    } finally {
      set({ isLoading: false });
    }
  },

  // Logs actions
  fetchLogs: async (status?: string) => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;

    try {
      set({ logsLoading: true });
      const statusFilter = status ?? get().logsStatusFilter;
      const result = await GetLogs(selectedEndpointSlug, 0, 50, statusFilter === 'all' ? '' : statusFilter);
      set({
        logs: result.logs || [],
        logsHasMore: result.hasMore,
        logsStatusFilter: statusFilter,
      });
    } catch (err) {
      set({ error: `Failed to fetch logs: ${err}` });
    } finally {
      set({ logsLoading: false });
    }
  },

  fetchLogStats: async () => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;

    try {
      const stats = await GetLogStats(selectedEndpointSlug);
      set({ logStats: stats });
    } catch (err) {
      // Stats are not critical, don't show error
      set({ logStats: null });
    }
  },

  loadMoreLogs: async (status?: string) => {
    const { selectedEndpointSlug, logs, logsHasMore, logsLoading } = get();
    if (!selectedEndpointSlug || !logsHasMore || logsLoading) return;

    try {
      set({ logsLoading: true });
      const statusFilter = status ?? get().logsStatusFilter;
      const result = await GetLogs(selectedEndpointSlug, logs.length, 50, statusFilter === 'all' ? '' : statusFilter);
      set({
        logs: [...logs, ...(result.logs || [])],
        logsHasMore: result.hasMore,
      });
    } catch (err) {
      set({ error: `Failed to load more logs: ${err}` });
    } finally {
      set({ logsLoading: false });
    }
  },

  setSelectedLog: (log: RequestLogEntry | null) => {
    set({ selectedLog: log });
  },

  setLogsStatusFilter: (status: string) => {
    set({ logsStatusFilter: status });
    get().fetchLogs(status);
  },

  deleteLogs: async () => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;

    try {
      set({ logsLoading: true });
      await DeleteLogs(selectedEndpointSlug);
      set({
        logs: [],
        logStats: null,
        logsHasMore: false,
      });
      await get().fetchLogStats();
    } catch (err) {
      set({ error: `Failed to delete logs: ${err}` });
    } finally {
      set({ logsLoading: false });
    }
  },

  // Manual review actions
  fetchManualReviews: async (status?: string) => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;

    try {
      set({ manualReviewsLoading: true });
      const statusFilter = status ?? get().reviewsStatusFilter;
      const result = await GetManualReviews(
        selectedEndpointSlug,
        statusFilter === 'all' ? '' : statusFilter,
      );
      set({ manualReviews: result || [] });
    } catch (err) {
      set({ error: `Failed to fetch manual reviews: ${err}` });
    } finally {
      set({ manualReviewsLoading: false });
    }
  },

  setSelectedReview: (review: ManualReviewEntry | null) => {
    set({ selectedReview: review });
  },

  setReviewsStatusFilter: (status: string) => {
    set({ reviewsStatusFilter: status });
    get().fetchManualReviews(status);
  },

  approveManualReview: async (reviewId: string) => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;
    try {
      await ApproveManualReview(selectedEndpointSlug, reviewId);
      // The row's status changed — refresh so it leaves the current filter.
      await get().fetchManualReviews();
    } catch (err) {
      set({ error: `Failed to approve request: ${err}` });
      throw err;
    }
  },

  rejectManualReview: async (reviewId: string, reason: string) => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) return;
    try {
      await RejectManualReview(selectedEndpointSlug, reviewId, reason);
      await get().fetchManualReviews();
    } catch (err) {
      set({ error: `Failed to reject request: ${err}` });
      throw err;
    }
  },

  // Sent-for-review actions — the client's own manual-review ledger. Unlike
  // manual reviews these are cross-endpoint and identity-scoped (the Go
  // backend filters by the logged-in user), so there is no endpoint guard.
  // Always fetches the full list (two consumers — the sidebar's thread view
  // and SentReviewsView's status-filtered list — share one store field, and
  // server-side filtering would drop just-resolved rows out of the sidebar
  // during reconciles). Status filtering happens client-side.
  fetchSentReviews: async () => {
    try {
      set({ sentReviewsLoading: true });
      const result = await GetSentReviews('');
      const next = result || [];
      // Skip the array-reference replacement when the wire payload is
      // structurally equal to what we already have so subscribers don't
      // re-render on a no-op reconcile.
      if (sentReviewsEqual(get().sentReviews, next)) {
        set({ sentReviewsLoading: false });
        return;
      }
      set({
        sentReviews: next,
        sentReviewThreads: computeSentReviewThreads(next),
        sentReviewsLoading: false,
      });
    } catch (err) {
      set({ error: `Failed to fetch sent reviews: ${err}`, sentReviewsLoading: false });
    }
  },

  applyResolvedEvent: (payload: ManualReviewResolvedPayload) => {
    if (!payload || !payload.reviewId) return;

    // Defence-in-depth identity check. The Go emit site does not currently
    // include `identity`, so this is a no-op today — but if a future change
    // adds it, mismatched payloads (e.g. an event from a previous session's
    // identity arriving after a logout/login) drop without polluting state.
    const id = get().currentIdentity;
    if (id && payload.identity && payload.identity !== id) return;

    const reviewId = payload.reviewId;
    const incomingStatus = payload.status ?? '';
    const rows = get().sentReviews;
    const idx = rows.findIndex((r) => r.reviewId === reviewId);

    if (idx === -1) {
      // Row not in current view (different filter, or never fetched). The
      // event only carries status/owner/slug — not the full row — so we
      // can't synthesize a row to insert. Schedule a reconcile so the
      // filtered view re-queries the backend.
      scheduleReconcile(get);
      return;
    }

    if (rows[idx].status === incomingStatus && incomingStatus !== '') {
      // Already in the resolved state — no-op, no fetch, no array
      // replacement. This is the common case when the listener fires after
      // a previous reconcile has already landed the new state.
      return;
    }

    // The payload doesn't carry responseText/resolvedAt, so we can't
    // produce a correct in-place splice for approvals (which need
    // responseText) or rejections (which need rejectReason). Schedule a
    // reconcile so the row's auxiliary fields come from the Go ledger.
    scheduleReconcile(get);
  },

  setSelectedSentReview: (review: SentReviewEntry | null) => {
    set({ selectedSentReview: review });
  },

  setSentReviewsFilter: (status: string) => {
    // Pure view-layer filter — SentReviewsView reads it and filters the
    // full sentReviews list client-side. No refetch needed (the store
    // already holds every status); refetching here would also blow away
    // the cached full list during reconciles. See fetchSentReviews for the
    // rationale.
    set({ sentReviewsFilter: status });
  },

  markSentReviewStatus: async (reviewId: string, status: 'approved' | 'rejected', reason: string) => {
    try {
      await SetSentReviewStatus(reviewId, status, reason);
      // The entry's status changed — refresh so it leaves the current filter.
      await get().fetchSentReviews();
    } catch (err) {
      set({ error: `Failed to update review: ${err}` });
      throw err;
    }
  },

  saveSentReviewNote: async (reviewId: string, note: string) => {
    try {
      await SetSentReviewNote(reviewId, note);
      await get().fetchSentReviews();
      // Keep an open detail panel in step with the saved note.
      const refreshed = get().sentReviews.find((r) => r.reviewId === reviewId);
      if (refreshed) set({ selectedSentReview: refreshed });
    } catch (err) {
      set({ error: `Failed to save note: ${err}` });
      throw err;
    }
  },

  deleteSentReview: async (reviewId: string) => {
    try {
      await DeleteSentReview(reviewId);
      // If we just deleted the currently-active chat, fall back to the live
      // pane — the surface can't render a row that no longer exists.
      const active = get().activeChat;
      if (active.kind === 'review' && active.reviewId === reviewId) {
        get().setActiveChat({ kind: 'live' });
      }
      await get().fetchSentReviews();
    } catch (err) {
      set({ error: `Failed to delete review: ${err}` });
      throw err;
    }
  },

  // Create endpoint actions
  setCreateDialogOpen: (open: boolean) => {
    set({ isCreateDialogOpen: open });
  },

  checkEndpointExists: async (name: string) => {
    try {
      const result = await CheckEndpointExists(name);
      // Result is [slug, exists] tuple
      if (Array.isArray(result)) {
        return { slug: result[0] as string, exists: result[1] as boolean };
      }
      // Handle case where Go returns single value
      return { slug: String(result), exists: false };
    } catch (err) {
      return { slug: '', exists: false };
    }
  },

  createEndpoint: async (request) => {
    try {
      set({ isCreatingEndpoint: true, error: null });

      // Create the endpoint request object
      const req = main.CreateEndpointRequest.createFrom({
        name: request.name,
        type: request.type,
        description: request.description || '',
        version: request.version || '1.0.0',
      });

      // Call backend to create endpoint
      const slug = await CreateEndpoint(req);

      // Optimistic UI: Add new endpoint to state immediately
      // This prevents the jarring empty state while waiting for file watcher
      const newEndpoint = main.EndpointInfo.createFrom({
        slug,
        name: request.name,
        type: request.type,
        description: request.description || '',
        enabled: true,
        version: request.version || '1.0.0',
        hasPolicies: false,
      });
      set((state) => ({
        endpoints: [...state.endpoints, newEndpoint],
      }));

      // Don't call reloadEndpoints() - let the file watcher handle the refresh
      // naturally. This avoids the race condition that causes empty state.

      // Close dialog
      set({ isCreateDialogOpen: false });

      // Select the new endpoint
      await get().selectEndpoint(slug);

      // Switch to Code tab to encourage editing
      set({ activeTab: 'code' });

      return slug;
    } catch (err) {
      set({ error: `Failed to create endpoint: ${err}` });
      throw err;
    } finally {
      set({ isCreatingEndpoint: false });
    }
  },

  // Chat actions
  setChatSelectedModel: (model: NetworkAgentInfo | null) => {
    if (get().chatSelectedModel === model) return;
    set({ chatSelectedModel: model });
  },

  setChatSelectedSources: (sources: EndpointInfo[]) => {
    set({ chatSelectedSources: sources });
  },

  toggleChatSource: (source: EndpointInfo) => {
    const current = get().chatSelectedSources;
    const exists = current.some((s) => s.slug === source.slug);
    set({
      chatSelectedSources: exists
        ? current.filter((s) => s.slug !== source.slug)
        : [...current, source],
    });
  },

  refreshAggregatorURL: async () => {
    const url = await GetAggregatorURL().catch(() => '');
    set({ aggregatorURL: url || null });
  },

  fetchNetworkAgents: async (force) => {
    const { networkAgentsLoading, networkAgentsLastFetchedAt } = get();
    if (networkAgentsLoading) return;
    const NETWORK_AGENTS_TTL_MS = 10_000;
    if (
      !force &&
      networkAgentsLastFetchedAt !== null &&
      Date.now() - networkAgentsLastFetchedAt < NETWORK_AGENTS_TTL_MS
    ) {
      return;
    }
    set({ networkAgentsLoading: true });
    try {
      const agents = (await ListNetworkAgents()) || [];
      const unchanged = networkAgentsEqual(get().networkAgents, agents);
      set({
        ...(unchanged ? {} : { networkAgents: agents }),
        networkAgentsLoading: false,
        networkAgentsLastFetchedAt: Date.now(),
      });
    } catch (err) {
      // Swallow: the network list is supplementary; the local agent list still
      // works when the hub is unreachable, so don't surface to the error banner.
      set({ networkAgentsLoading: false });
    }
  },

  // Delete endpoint actions
  setDeleteDialogOpen: (open: boolean) => {
    set({ isDeleteDialogOpen: open });
  },

  deleteEndpoint: async () => {
    const state = get();
    if (!state.selectedEndpointSlug) {
      set({ error: 'No endpoint selected' });
      return;
    }

    const slugToDelete = state.selectedEndpointSlug;
    const patch = removedSlugPatch(state, slugToDelete);

    // Optimistic remove: update UI immediately so the endpoint disappears at once.
    // The file watcher will confirm the removal when it fires.
    set({
      isDeletingEndpoint: true,
      isDeleteDialogOpen: false,
      error: null,
      ...patch,
    });

    try {
      await DeleteEndpoint(slugToDelete);
      await get().selectEndpoint(patch.endpoints.length > 0 ? patch.endpoints[0].slug : null);
    } catch (err) {
      // Rollback: restore the original list so the endpoint reappears in the UI.
      set({
        error: `Failed to delete endpoint: ${err}`,
        endpoints: state.endpoints,
        chatSelectedSources: state.chatSelectedSources,
      });
      throw err;
    } finally {
      set({ isDeletingEndpoint: false });
    }
  },

  // Rename endpoint actions
  setRenameDialogOpen: (open: boolean) => {
    set({ isRenameDialogOpen: open });
  },

  renameEndpoint: async (newName: string) => {
    const { selectedEndpointSlug } = get();
    if (!selectedEndpointSlug) {
      set({ error: 'No endpoint selected' });
      throw new Error('No endpoint selected');
    }

    try {
      set({ isRenamingEndpoint: true, error: null });
      const newSlug = await RenameEndpoint(selectedEndpointSlug, newName);
      // The folder (slug) changed: refresh the list and re-select the
      // endpoint under its new slug so the detail view stays in sync.
      await get().fetchEndpoints();
      await get().selectEndpoint(newSlug);
      set({ isRenameDialogOpen: false });
      return newSlug;
    } catch (err) {
      set({ error: `Failed to rename endpoint: ${err}` });
      throw err;
    } finally {
      set({ isRenamingEndpoint: false });
    }
  },

  // Library actions
  fetchLibraryPackages: async () => {
    try {
      set({ libraryLoading: true, libraryError: null });
      const packages = await GetLibraryPackages();
      set({ libraryPackages: packages || [] });
    } catch (err) {
      set({ libraryError: `Failed to load packages: ${err}` });
    } finally {
      set({ libraryLoading: false });
    }
  },

  installLibraryPackage: async (slug: string, downloadUrl: string, configValues?: Record<string, string>) => {
    try {
      set({ installingPackageSlug: slug });
      // The backend auto-triggers RunEndpointSetup if setup.yaml exists.
      // Setup flow state is managed entirely by event listeners (setupflow:*),
      // not set here, to avoid a race where this code overwrites prompt data
      // that the goroutine has already emitted.
      await InstallLibraryPackage(slug, downloadUrl, configValues ?? {});
      await get().fetchEndpoints();
    } catch (err) {
      set({ error: `Failed to install package: ${err}` });
      throw err;
    } finally {
      set({ installingPackageSlug: null });
    }
  },

  uninstallLibraryPackage: async (slug: string) => {
    const state = get();
    const patch = removedSlugPatch(state, slug);

    // Optimistic remove: update UI immediately so the endpoint disappears at once.
    // The file watcher will confirm the removal when it fires.
    set({ installingPackageSlug: slug, ...patch });

    try {
      await DeleteEndpoint(slug);
      if (get().selectedEndpointSlug === slug) {
        await get().selectEndpoint(patch.endpoints.length > 0 ? patch.endpoints[0].slug : null);
      }
    } catch (err) {
      // Rollback: restore the original list so the endpoint reappears in the UI.
      set({
        error: `Failed to uninstall package: ${err}`,
        endpoints: state.endpoints,
        chatSelectedSources: state.chatSelectedSources,
      });
    } finally {
      set({ installingPackageSlug: null });
    }
  },

  // Setup flow actions
  runSetup: async (slug: string, force: boolean = false) => {
    // Don't set state optimistically here — the Go backend emits 'setupflow:started'
    // synchronously before launching the goroutine, so that event drives the UI.
    try {
      await RunEndpointSetup(slug, force);
    } catch (err) {
      set({ setupFlow: { ...SETUP_FLOW_CLEARED, error: `Failed to start setup: ${err}` } });
    }
  },

  respondToSetupPrompt: async (value: string) => {
    try {
      set(s => ({ setupFlow: { ...s.setupFlow, prompt: null } }));
      await RespondToSetupPrompt(value);
    } catch (err) {
      set(s => ({ setupFlow: { ...s.setupFlow, error: `Failed to respond: ${err}` } }));
    }
  },

  respondToSetupSelect: async (value: string) => {
    try {
      set(s => ({ setupFlow: { ...s.setupFlow, select: null } }));
      await RespondToSetupSelect(value);
    } catch (err) {
      set(s => ({ setupFlow: { ...s.setupFlow, error: `Failed to respond: ${err}` } }));
    }
  },

  respondToSetupConfirm: async (confirmed: boolean) => {
    try {
      set(s => ({ setupFlow: { ...s.setupFlow, confirm: null } }));
      await RespondToSetupConfirm(confirmed);
    } catch (err) {
      set(s => ({ setupFlow: { ...s.setupFlow, error: `Failed to respond: ${err}` } }));
    }
  },

  cancelSetup: async () => {
    try {
      await CancelSetup();
      set({ setupFlow: { ...SETUP_FLOW_CLEARED } });
    } catch (err) {
      set(s => ({ setupFlow: { ...s.setupFlow, error: `Failed to cancel: ${err}` } }));
    }
  },

  clearSetupFlow: () => {
    set({ setupFlow: { ...SETUP_FLOW_CLEARED } });
  },
}));
