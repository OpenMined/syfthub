import { create } from 'zustand';
import { EventsOff, EventsOn } from '../../wailsjs/runtime/runtime';
import { parseFrontmatter } from '../lib/markdown';
import { main } from '../../wailsjs/go/models';
import {
  GetStatus,
  GetEndpoints,
  GetConfig,
  GetAggregatorURL,
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
  CreateEndpoint,
  CheckEndpointExists,
  DeleteEndpoint,
  GetUserAggregators,
  GetMarketplacePackages,
  InstallMarketplacePackage,
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
export type CreateEndpointRequest = main.CreateEndpointRequest;
export type ChatRequest = main.ChatRequest;
export type MarketplacePackage = main.MarketplacePackage;
export type SetupStatusInfo = main.SetupStatusInfo;
export type SetupSpecInfo = main.SetupSpecInfo;
export type SetupStepInfo = main.SetupStepInfo;

// TS-only UI label set by the setupflow:complete listener. Not a Go wire value.
export const SETUP_COMPLETE_STATUS = 'Setup complete' as const;

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
  activeTab: 'settings' | 'code' | 'docs' | 'logs';
  settingsSection: 'overview' | 'environment' | 'dependencies' | 'policies';
  mainView: 'endpoints' | 'chat';
  showMarketplace: boolean;

  // Logs state
  logs: RequestLogEntry[];
  logStats: LogStats | null;
  logsLoading: boolean;
  logsHasMore: boolean;
  selectedLog: RequestLogEntry | null;
  logsStatusFilter: string;

  // Create endpoint state
  isCreateDialogOpen: boolean;
  isCreatingEndpoint: boolean;
  lastOptimisticAddTime: number | null;

  // Delete endpoint state
  isDeleteDialogOpen: boolean;
  isDeletingEndpoint: boolean;

  // Chat state
  chatSelectedModel: EndpointInfo | null;
  chatSelectedSources: EndpointInfo[];
  aggregatorURL: string | null;

  // Marketplace state
  marketplacePackages: MarketplacePackage[];
  marketplaceLoading: boolean;
  marketplaceError: string | null;
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
  setActiveTab: (tab: 'settings' | 'code' | 'docs' | 'logs') => void;
  setSettingsSection: (section: 'overview' | 'environment' | 'dependencies' | 'policies') => void;
  setMainView: (view: 'endpoints' | 'chat') => void;
  setShowMarketplace: (show: boolean) => void;

  // Actions - Logs
  fetchLogs: (status?: string) => Promise<void>;
  fetchLogStats: () => Promise<void>;
  loadMoreLogs: (status?: string) => Promise<void>;
  setSelectedLog: (log: RequestLogEntry | null) => void;
  setLogsStatusFilter: (status: string) => void;
  deleteLogs: () => Promise<void>;

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
  setChatSelectedModel: (model: EndpointInfo | null) => void;
  setChatSelectedSources: (sources: EndpointInfo[]) => void;
  toggleChatSource: (source: EndpointInfo) => void;
  refreshAggregatorURL: () => Promise<void>;

  // Actions - Marketplace
  fetchMarketplacePackages: () => Promise<void>;
  installMarketplacePackage: (slug: string, downloadUrl: string) => Promise<void>;
  uninstallMarketplacePackage: (slug: string) => Promise<void>;

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
  showMarketplace: false,

  // Logs initial state
  logs: [],
  logStats: null,
  logsLoading: false,
  logsHasMore: false,
  selectedLog: null,
  logsStatusFilter: 'all',

  // Create endpoint initial state
  isCreateDialogOpen: false,
  isCreatingEndpoint: false,
  lastOptimisticAddTime: null,

  // Delete endpoint initial state
  isDeleteDialogOpen: false,
  isDeletingEndpoint: false,

  // Chat initial state
  chatSelectedModel: null,
  chatSelectedSources: [],
  aggregatorURL: null,

  // Marketplace initial state
  marketplacePackages: [],
  marketplaceLoading: false,
  marketplaceError: null,
  installingPackageSlug: null,

  // Setup flow initial state
  setupFlow: { ...SETUP_FLOW_CLEARED },

  // Core actions
  initialize: async () => {
    try {
      set({ isInitializing: true, error: null });

      // Wait for SpaceURL to be set (fetched async during Wails startup)
      const maxConfigAttempts = 50; // 5 seconds max
      let configAttempts = 0;
      let config;
      while (configAttempts < maxConfigAttempts) {
        config = await GetConfig();
        if (config.spaceUrl) {
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 100));
        configAttempts++;
      }

      if (!config?.spaceUrl) {
        throw new Error('Configuration incomplete - SpaceURL not set. Check your API key and connection.');
      }

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

      // Now reload endpoints from disk
      await ReloadEndpoints();

      // Fetch all data including aggregator URL
      await Promise.all([
        get().fetchStatus(),
        get().fetchEndpoints(),
        get().fetchConfig(),
        get().refreshAggregatorURL(),
      ]);

      // Deregister any previous listeners before re-registering so multiple
      // initialize() calls (e.g. reconnect, re-login) don't stack handlers.
      EventsOff(
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
        // Listen for file watcher events (auto-refresh when files change)
        EventsOn('app:endpoints-changed', (incomingEndpoints: EndpointInfo[]) => {
          const { endpoints: currentEndpoints, lastOptimisticAddTime } = get();
          const gracePeriod = 3000; // 3 seconds
          const inGracePeriod = lastOptimisticAddTime && (Date.now() - lastOptimisticAddTime) < gracePeriod;

          // During grace period, reject any update that would reduce our endpoint count
          // This protects against file watcher intermediate states during endpoint creation
          if (inGracePeriod) {
            if (!incomingEndpoints || incomingEndpoints.length < currentEndpoints.length) {
              return; // Reject - would lose endpoints
            }
            // Accept but keep grace period active (don't clear lastOptimisticAddTime)
            set({ endpoints: incomingEndpoints });
            return;
          }

          set({ endpoints: incomingEndpoints || [] });
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

        // Listen for new log events (real-time log updates)
        EventsOn('app:new-log', (entry: RequestLogEntry) => {
          const { selectedEndpointSlug, logs } = get();
          // Only add to logs if viewing the same endpoint
          if (entry.endpointSlug === selectedEndpointSlug) {
            set({ logs: [entry, ...logs] });
            // Debounce stats refresh — one IPC call per burst, not per log entry
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
      const endpoints = await GetEndpoints();
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
      });
      return;
    }

    try {
      set({ isLoading: true, error: null, showMarketplace: false });

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
    set({ mainView: view, showMarketplace: false });
  },

  setShowMarketplace: (show) => {
    if (show) {
      set({ showMarketplace: true, selectedEndpointSlug: null, selectedEndpointDetail: null });
    } else {
      set({ showMarketplace: false });
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
      // Start grace period BEFORE backend call - file watcher may fire during CreateEndpoint
      set({ isCreatingEndpoint: true, error: null, lastOptimisticAddTime: Date.now() });

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
  setChatSelectedModel: (model: EndpointInfo | null) => {
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

  // Aggregator URL refresh — prefers the user's default custom aggregator URL;
  // falls back to the SDK default ({syfthubURL}/aggregator/api/v1) when no
  // custom aggregator is configured or the list call fails.
  refreshAggregatorURL: async () => {
    try {
      const aggregators = await GetUserAggregators();
      const defaultAgg = aggregators?.find((a) => a.is_default) ?? null;
      // If no custom default, fall back to the SDK-derived URL
      const url = defaultAgg?.url || (await GetAggregatorURL().catch(() => ''));
      set({ aggregatorURL: url || null });
    } catch {
      // GetUserAggregators failed (e.g. not yet configured) — use SDK URL
      const url = await GetAggregatorURL().catch(() => '');
      set({ aggregatorURL: url || null });
    }
  },

  // Delete endpoint actions
  setDeleteDialogOpen: (open: boolean) => {
    set({ isDeleteDialogOpen: open });
  },

  deleteEndpoint: async () => {
    const { selectedEndpointSlug, endpoints } = get();
    if (!selectedEndpointSlug) {
      set({ error: 'No endpoint selected' });
      return;
    }

    const slugToDelete = selectedEndpointSlug;

    try {
      set({ isDeletingEndpoint: true, error: null });

      // Call backend to delete endpoint
      await DeleteEndpoint(slugToDelete);

      // Optimistic UI: Remove endpoint from state immediately
      const remainingEndpoints = endpoints.filter(ep => ep.slug !== slugToDelete);
      set({ endpoints: remainingEndpoints });

      // Close dialog
      set({ isDeleteDialogOpen: false });

      // Select another endpoint or clear selection
      if (remainingEndpoints.length > 0) {
        await get().selectEndpoint(remainingEndpoints[0].slug);
      } else {
        await get().selectEndpoint(null);
      }
    } catch (err) {
      set({ error: `Failed to delete endpoint: ${err}` });
      throw err;
    } finally {
      set({ isDeletingEndpoint: false });
    }
  },

  // Marketplace actions
  fetchMarketplacePackages: async () => {
    try {
      set({ marketplaceLoading: true, marketplaceError: null });
      const packages = await GetMarketplacePackages();
      set({ marketplacePackages: packages || [] });
    } catch (err) {
      set({ marketplaceError: `Failed to load packages: ${err}` });
    } finally {
      set({ marketplaceLoading: false });
    }
  },

  installMarketplacePackage: async (slug: string, downloadUrl: string) => {
    try {
      set({ installingPackageSlug: slug });
      // The backend auto-triggers RunEndpointSetup if setup.yaml exists.
      // Setup flow state is managed entirely by event listeners (setupflow:*),
      // not set here, to avoid a race where this code overwrites prompt data
      // that the goroutine has already emitted.
      await InstallMarketplacePackage(slug, downloadUrl);
      await get().fetchEndpoints();
    } finally {
      set({ installingPackageSlug: null });
    }
  },

  uninstallMarketplacePackage: async (slug: string) => {
    try {
      set({ installingPackageSlug: slug });
      await DeleteEndpoint(slug);

      // Optimistic UI: remove from endpoints immediately (mirrors deleteEndpoint)
      const remainingEndpoints = get().endpoints.filter(ep => ep.slug !== slug);
      set({ endpoints: remainingEndpoints });

      // If the uninstalled endpoint was selected, navigate away
      if (get().selectedEndpointSlug === slug) {
        if (remainingEndpoints.length > 0) {
          await get().selectEndpoint(remainingEndpoints[0].slug);
        } else {
          await get().selectEndpoint(null);
        }
      }
    } catch (err) {
      set({ error: `Failed to uninstall package: ${err}` });
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
