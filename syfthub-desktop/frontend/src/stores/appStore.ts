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
  CreateEndpoint,
  CheckEndpointExists,
  DeleteEndpoint,
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
  mainView: 'endpoints' | 'chat';
  // Which sub-view the chat surface shows: the live chat, or the cross-endpoint
  // "Sent for Review" ledger of manual-review holds the user submitted.
  chatSubView: 'chat' | 'reviews';
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

  // Create endpoint state
  isCreateDialogOpen: boolean;
  isCreatingEndpoint: boolean;

  // Delete endpoint state
  isDeleteDialogOpen: boolean;
  isDeletingEndpoint: boolean;

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

  // Actions - Core
  initialize: () => Promise<void>; // Initial app load
  fetchStatus: () => Promise<void>;
  fetchEndpoints: () => Promise<void>;
  fetchConfig: () => Promise<void>;
  startService: () => Promise<void>;
  stopService: () => Promise<void>;
  reloadEndpoints: () => Promise<void>;

  // Actions - Selection
  selectEndpoint: (slug: string | null) => Promise<void>;
  setActiveTab: (tab: 'settings' | 'code' | 'docs' | 'logs' | 'requests') => void;
  setSettingsSection: (section: 'overview' | 'environment' | 'dependencies' | 'policies' | 'skills') => void;
  setMainView: (view: 'endpoints' | 'chat') => void;
  setChatSubView: (view: 'chat' | 'reviews') => void;
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
  fetchSentReviews: (status?: string) => Promise<void>;
  setSelectedSentReview: (review: SentReviewEntry | null) => void;
  setSentReviewsFilter: (status: string) => void;
  markSentReviewStatus: (reviewId: string, status: 'approved' | 'rejected', reason: string) => Promise<void>;
  saveSentReviewNote: (reviewId: string, note: string) => Promise<void>;

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
  mainView: 'endpoints',
  chatSubView: 'chat',
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
  sentReviewsLoading: false,
  selectedSentReview: null,
  sentReviewsFilter: 'pending',

  // Create endpoint initial state
  isCreateDialogOpen: false,
  isCreatingEndpoint: false,

  // Delete endpoint initial state
  isDeleteDialogOpen: false,
  isDeletingEndpoint: false,

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
      ]);

      // Deregister any previous listeners before re-registering so multiple
      // initialize() calls (e.g. reconnect, re-login) don't stack handlers.
      EventsOff(
        'app:config-ready',
        'app:endpoints-changed',
        'app:new-log',
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

          // Skip no-op updates so Zustand doesn't re-render when the list hasn't changed.
          // Compare JSON fingerprints (not just slugs) so metadata-only changes are picked up.
          const currentKey = JSON.stringify(get().endpoints);
          const incomingKey = JSON.stringify(agentOnly);
          if (currentKey === incomingKey) return;

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

  setChatSubView: (view) => {
    set({ chatSubView: view });
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
  fetchSentReviews: async (status?: string) => {
    try {
      set({ sentReviewsLoading: true });
      const statusFilter = status ?? get().sentReviewsFilter;
      const result = await GetSentReviews(statusFilter === 'all' ? '' : statusFilter);
      set({ sentReviews: result || [] });
    } catch (err) {
      set({ error: `Failed to fetch sent reviews: ${err}` });
    } finally {
      set({ sentReviewsLoading: false });
    }
  },

  setSelectedSentReview: (review: SentReviewEntry | null) => {
    set({ selectedSentReview: review });
  },

  setSentReviewsFilter: (status: string) => {
    set({ sentReviewsFilter: status });
    get().fetchSentReviews(status);
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
      // Skip the array-reference replacement when the wire payload is unchanged
      // so subscribers (and the ModelSelector's filteredModels useMemo) don't
      // re-render on a no-op refresh. Mirrors the app:endpoints-changed guard.
      const unchanged = JSON.stringify(get().networkAgents) === JSON.stringify(agents);
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
