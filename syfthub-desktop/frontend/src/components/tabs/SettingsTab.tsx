import { useState, useEffect, useCallback, useRef } from 'react';
import { OctagonAlert, TriangleAlert } from 'lucide-react';
import { useAppStore, type EnvVar } from '../../stores/appStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { GetDependencies, AddDependency, DeleteDependency, OpenEndpointFolder, ListPolicyFiles, GetPolicyFileYaml, SavePolicyFileYaml, DeletePolicyFile, CreatePolicyFile } from '../../../wailsjs/go/main/App';
import { main } from '../../../wailsjs/go/models';
import Editor from '@monaco-editor/react';

type Dependency = main.Dependency;
type PolicyFileInfo = main.PolicyFileInfo;
type SettingsSection = 'overview' | 'environment' | 'dependencies' | 'policies';

// Navigation items
const navItems: { id: SettingsSection; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'environment', label: 'Environment' },
  { id: 'dependencies', label: 'Dependencies' },
  { id: 'policies', label: 'Policies' },
];

export function SettingsTab() {
  const { settingsSection, setSettingsSection } = useAppStore();

  return (
    <div className="h-full flex">
      {/* Settings Navigation Sidebar */}
      <nav className="w-36 flex-shrink-0 border-r border-border/30 py-2">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setSettingsSection(item.id)}
            className={`
              w-full text-left px-4 py-2 text-sm transition-colors
              ${settingsSection === item.id
                ? 'bg-secondary/50 text-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-card/50'
              }
            `}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {/* Section Content */}
      <div className="flex-1 overflow-y-auto">
        {settingsSection === 'overview' && <OverviewSection />}
        {settingsSection === 'environment' && <EnvironmentSection />}
        {settingsSection === 'dependencies' && <DependenciesSection />}
        {settingsSection === 'policies' && <PoliciesSection />}
      </div>
    </div>
  );
}

// ============================================================================
// OVERVIEW SECTION
// ============================================================================
function OverviewSection() {
  const {
    selectedEndpointSlug,
    selectedEndpointDetail,
    isSaving,
    updateOverview,
    setDeleteDialogOpen,
  } = useAppStore();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [endpointType, setEndpointType] = useState('');
  const [version, setVersion] = useState('');
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    if (selectedEndpointDetail) {
      setName(selectedEndpointDetail.name || '');
      setDescription(selectedEndpointDetail.description || '');
      setEndpointType(selectedEndpointDetail.type || 'model');
      setVersion(selectedEndpointDetail.version || '');
      setIsDirty(false);
    }
  }, [selectedEndpointDetail]);

  if (!selectedEndpointDetail) return null;

  const handleChange = (setter: (v: string) => void) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    setter(e.target.value);
    setIsDirty(true);
  };

  const handleSave = async () => {
    try {
      await updateOverview(name, description, endpointType, version);
      setIsDirty(false);
    } catch {
      // Error handled by store
    }
  };

  const handleOpenFolder = async () => {
    if (selectedEndpointSlug) {
      await OpenEndpointFolder(selectedEndpointSlug);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <SectionHeader
        title="Overview"
        action={
          isDirty && (
            <Button size="sm" onClick={handleSave} disabled={isSaving} className="h-7 text-xs">
              {isSaving ? 'Saving...' : 'Save'}
            </Button>
          )
        }
      />

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Name">
            <Input
              value={name}
              onChange={handleChange(setName)}
              placeholder="Endpoint name"
              className="h-9"
            />
          </Field>
          <Field label="Version">
            <Input
              value={version}
              onChange={handleChange(setVersion)}
              placeholder="1.0.0"
              className="h-9"
            />
          </Field>
        </div>

        <Field label="Description">
          <textarea
            value={description}
            onChange={handleChange(setDescription)}
            placeholder="Endpoint description"
            rows={3}
            className="w-full rounded-md bg-background border border-input text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-ring/50"
          />
        </Field>

        <Field label="Type">
          <Select value={endpointType} onValueChange={setEndpointType}>
            <SelectTrigger className="w-full h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Endpoint Type</SelectLabel>
                <SelectItem value="model">Model</SelectItem>
                <SelectItem value="data_source">Data Source</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
      </div>

      {/* File System */}
      <div className="pt-4 border-t border-border/30">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-foreground">File System</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Slug: <code className="text-secondary-foreground">{selectedEndpointDetail.slug}</code>
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleOpenFolder}
            className="h-8"
          >
            <FolderIcon className="w-4 h-4 mr-1.5" />
            Open Folder
          </Button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="pt-6 mt-6 border-t border-destructive/20">
        <h3 className="text-sm font-medium text-destructive mb-3">Danger Zone</h3>
        <div className="p-4 rounded-lg border border-destructive/30 bg-destructive/5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-foreground">Delete this endpoint</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Once deleted, this endpoint and all its files cannot be recovered.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeleteDialogOpen(true)}
              className="h-8 border-destructive/50 text-destructive hover:bg-destructive/10"
            >
              <TrashIcon className="w-4 h-4 mr-1.5" />
              Delete Endpoint
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// ENVIRONMENT SECTION
// ============================================================================
function EnvironmentSection() {
  const { envVars, isSaving, setEnvVar, deleteEnvVar } = useAppStore();
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  const handleAdd = async () => {
    if (!newKey.trim()) return;
    try {
      await setEnvVar(newKey.trim(), newValue);
      setNewKey('');
      setNewValue('');
    } catch {
      // Error handled by store
    }
  };

  const handleDelete = async (key: string) => {
    try {
      await deleteEnvVar(key);
    } catch {
      // Error handled by store
    }
  };

  return (
    <div className="p-6 space-y-6">
      <SectionHeader title="Environment Variables" />

      {/* Existing variables */}
      {envVars.length > 0 ? (
        <div className="space-y-2">
          {envVars.map((env: EnvVar) => (
            <div
              key={env.key}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-card/50 border border-border/50"
            >
              <span className="font-mono text-sm text-foreground min-w-[120px] truncate">
                {env.key}
              </span>
              <span className="text-muted-foreground">=</span>
              <span className="flex-1 font-mono text-sm text-muted-foreground truncate">
                {env.value || '(empty)'}
              </span>
              <button
                onClick={() => handleDelete(env.key)}
                disabled={isSaving}
                className="p-1.5 text-muted-foreground hover:text-destructive transition-colors rounded hover:bg-secondary/50"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-8 text-center">
          <p className="text-sm text-muted-foreground">No environment variables defined</p>
          <p className="text-xs text-muted-foreground/70 mt-1">Add variables below to configure your endpoint</p>
        </div>
      )}

      {/* Add new variable */}
      <div className="pt-4 border-t border-border/30">
        <p className="text-xs text-muted-foreground mb-3">Add new variable</p>
        <div className="flex items-center gap-2">
          <Input
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="KEY"
            className="flex-1 h-9 font-mono"
          />
          <span className="text-muted-foreground">=</span>
          <Input
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder="value"
            className="flex-1 h-9 font-mono"
          />
          <Button
            size="sm"
            onClick={handleAdd}
            disabled={isSaving || !newKey.trim()}
            className="h-9 px-3"
          >
            <PlusIcon className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// DEPENDENCIES SECTION
// ============================================================================
function DependenciesSection() {
  const { selectedEndpointSlug } = useAppStore();
  const [dependencies, setDependencies] = useState<Dependency[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newPkg, setNewPkg] = useState('');
  const [newVersion, setNewVersion] = useState('');

  const fetchDeps = async () => {
    if (!selectedEndpointSlug) return;
    setLoading(true);
    try {
      const deps = await GetDependencies(selectedEndpointSlug);
      setDependencies(deps || []);
    } catch {
      setDependencies([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDeps();
  }, [selectedEndpointSlug]);

  const handleAdd = async () => {
    if (!selectedEndpointSlug || !newPkg.trim()) return;
    setSaving(true);
    try {
      await AddDependency(selectedEndpointSlug, newPkg.trim(), newVersion.trim());
      setNewPkg('');
      setNewVersion('');
      await fetchDeps();
    } catch {
      // Error handled silently
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (pkg: string) => {
    if (!selectedEndpointSlug) return;
    setSaving(true);
    try {
      await DeleteDependency(selectedEndpointSlug, pkg);
      await fetchDeps();
    } catch {
      // Error handled silently
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <SectionHeader
        title="Dependencies"
        badge={loading ? undefined : `${dependencies.length}`}
      />

      {loading ? (
        <div className="flex items-center gap-3 py-8 justify-center text-muted-foreground">
          <div className="w-5 h-5 border-2 border-secondary border-t-primary rounded-full animate-spin" />
          <span className="text-sm">Loading dependencies...</span>
        </div>
      ) : dependencies.length > 0 ? (
        <div className="space-y-2">
          {dependencies.map((dep, index) => (
            <div
              key={`${dep.package}-${index}`}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-card/50 border border-border/50"
            >
              <span className="font-mono text-sm text-foreground flex-1 truncate">
                {dep.package}
              </span>
              <span className="font-mono text-xs text-muted-foreground min-w-[60px] text-right">
                {dep.version || 'latest'}
              </span>
              <button
                onClick={() => handleDelete(dep.package)}
                disabled={saving}
                className="p-1.5 text-muted-foreground hover:text-destructive transition-colors rounded hover:bg-secondary/50"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-8 text-center">
          <PackageIcon className="w-10 h-10 mx-auto mb-3 text-secondary" />
          <p className="text-sm text-muted-foreground">No dependencies found</p>
          <p className="text-xs text-muted-foreground/70 mt-1">Add packages below to get started</p>
        </div>
      )}

      {/* Add new dependency */}
      <div className="pt-4 border-t border-border/30">
        <p className="text-xs text-muted-foreground mb-3">Add new dependency</p>
        <div className="flex items-center gap-2">
          <Input
            value={newPkg}
            onChange={(e) => setNewPkg(e.target.value)}
            placeholder="package-name"
            className="flex-1 h-9 font-mono"
          />
          <Input
            value={newVersion}
            onChange={(e) => setNewVersion(e.target.value)}
            placeholder="version (optional)"
            className="w-36 h-9 font-mono text-xs"
          />
          <Button
            size="sm"
            onClick={handleAdd}
            disabled={saving || !newPkg.trim()}
            className="h-9 px-3"
          >
            <PlusIcon className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// POLICIES SECTION
// ============================================================================

// All supported policy types
const POLICY_TYPES = [
  { value: 'AccessGroupPolicy', label: 'Access Group', description: 'Controls access based on user group membership' },
  { value: 'RateLimitPolicy', label: 'Rate Limit', description: 'Limits requests per time window' },
  { value: 'TokenLimitPolicy', label: 'Token Limit', description: 'Limits token usage for LLM endpoints' },
  { value: 'PromptFilterPolicy', label: 'Prompt Filter', description: 'Filters requests based on prompt patterns' },
  { value: 'AttributionPolicy', label: 'Attribution', description: 'Tracks data usage for audit' },
  { value: 'ManualReviewPolicy', label: 'Manual Review', description: 'Requires manual approval' },
  { value: 'TransactionPolicy', label: 'Transaction', description: 'Manages credit-based transactions' },
  { value: 'AllOfPolicy', label: 'All Of (Composite)', description: 'ALL child policies must pass', isComposite: true },
  { value: 'AnyOfPolicy', label: 'Any Of (Composite)', description: 'At least ONE child policy must pass', isComposite: true },
  { value: 'NotPolicy', label: 'Not (Composite)', description: 'Inverts the wrapped policy', isComposite: true, isSingle: true },
] as const;

// Composite policy types that need child policy selection
const COMPOSITE_TYPES = ['AllOfPolicy', 'AnyOfPolicy', 'NotPolicy'];

// Policy type badge colors - using semantic chart colors
const policyTypeColors: Record<string, string> = {
  AccessGroupPolicy: 'bg-primary/20 text-primary',
  RateLimitPolicy: 'bg-chart-3/20 text-chart-3',
  TokenLimitPolicy: 'bg-chart-2/20 text-chart-2',
  PromptFilterPolicy: 'bg-chart-4/20 text-chart-4',
  AttributionPolicy: 'bg-cyan-500/20 text-cyan-400',
  ManualReviewPolicy: 'bg-orange-500/20 text-orange-400',
  TransactionPolicy: 'bg-pink-500/20 text-pink-400',
  AllOfPolicy: 'bg-indigo-500/20 text-indigo-400',
  AnyOfPolicy: 'bg-teal-500/20 text-teal-400',
  NotPolicy: 'bg-destructive/20 text-destructive',
  default: 'bg-secondary/50 text-muted-foreground',
};

function getPolicyTypeBadgeColor(type: string): string {
  return policyTypeColors[type] || policyTypeColors.default;
}

function formatPolicyType(type: string): string {
  // Convert AccessGroupPolicy -> Access Group
  return type.replace(/Policy$/, '').replace(/([A-Z])/g, ' $1').trim();
}

function PoliciesSection() {
  const { selectedEndpointSlug, selectedEndpointDetail } = useAppStore();
  const [policyFiles, setPolicyFiles] = useState<PolicyFileInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [currentFile, setCurrentFile] = useState<PolicyFileInfo | null>(null);
  const [yamlContent, setYamlContent] = useState('');
  const [originalYaml, setOriginalYaml] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showNewDialog, setShowNewDialog] = useState(false);
  // Delete policy dialog state
  const [policyToDelete, setPolicyToDelete] = useState<PolicyFileInfo | null>(null);
  // Discard changes dialog state
  const [showDiscardDialog, setShowDiscardDialog] = useState(false);
  // New policy form state
  const [newPolicyName, setNewPolicyName] = useState('');
  const [newPolicyType, setNewPolicyType] = useState('AccessGroupPolicy');
  const [selectedChildPolicies, setSelectedChildPolicies] = useState<string[]>([]);
  const [denyReason, setDenyReason] = useState('');

  // Fetch policy files for the list view
  const fetchPolicyFiles = useCallback(async () => {
    if (!selectedEndpointSlug) return;
    setLoading(true);
    try {
      const result = await ListPolicyFiles(selectedEndpointSlug);
      setPolicyFiles(result || []);
    } catch {
      setPolicyFiles([]);
    } finally {
      setLoading(false);
    }
  }, [selectedEndpointSlug]);

  // Fetch YAML content for a specific policy file
  const fetchPolicyYaml = async (filename: string) => {
    if (!selectedEndpointSlug) return;
    try {
      const content = await GetPolicyFileYaml(selectedEndpointSlug, filename);
      setYamlContent(content);
      setOriginalYaml(content);
      setError(null);
    } catch (err) {
      setError(`Failed to load: ${err}`);
    }
  };

  useEffect(() => {
    fetchPolicyFiles();
  }, [fetchPolicyFiles]);

  // Load YAML when editor opens with a file
  useEffect(() => {
    if (editorOpen && currentFile) {
      fetchPolicyYaml(currentFile.filename);
    }
  }, [editorOpen, currentFile, selectedEndpointSlug]);

  if (!selectedEndpointDetail) return null;

  const hasUnsavedChanges = yamlContent !== originalYaml;

  const handleEditorChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      setYamlContent(value);
      setError(null);
    }
  }, []);

  const handleEdit = (policy: PolicyFileInfo) => {
    setCurrentFile(policy);
    setYamlContent('');
    setOriginalYaml('');
    setError(null);
    setEditorOpen(true);
  };

  const handleDeleteClick = (policy: PolicyFileInfo) => {
    setPolicyToDelete(policy);
  };

  const handleDeleteConfirm = async () => {
    if (!selectedEndpointSlug || !policyToDelete) return;

    setDeleting(policyToDelete.filename);
    setPolicyToDelete(null);
    try {
      await DeletePolicyFile(selectedEndpointSlug, policyToDelete.filename);
      await fetchPolicyFiles();
    } catch (err) {
      console.error('Failed to delete policy:', err);
    } finally {
      setDeleting(null);
    }
  };

  const handleSave = async () => {
    if (!selectedEndpointSlug || !currentFile) return;
    setSaving(true);
    setError(null);
    try {
      await SavePolicyFileYaml(selectedEndpointSlug, currentFile.filename, yamlContent);
      setOriginalYaml(yamlContent);
      await fetchPolicyFiles(); // Refresh the list
    } catch (err) {
      setError(`${err}`);
    } finally {
      setSaving(false);
    }
  };

  // Use ref to always have access to the latest handleSave in the editor command
  const handleSaveRef = useRef(handleSave);
  useEffect(() => {
    handleSaveRef.current = handleSave;
  });

  const handleCreate = async () => {
    if (!selectedEndpointSlug || !newPolicyName.trim()) return;
    setSaving(true);
    try {
      const request = {
        name: newPolicyName.trim(),
        type: newPolicyType,
        childPolicies: COMPOSITE_TYPES.includes(newPolicyType) ? selectedChildPolicies : [],
        denyReason: newPolicyType === 'NotPolicy' ? denyReason : '',
      };
      await CreatePolicyFile(selectedEndpointSlug, request);
      // Reset form state
      setNewPolicyName('');
      setNewPolicyType('AccessGroupPolicy');
      setSelectedChildPolicies([]);
      setDenyReason('');
      setShowNewDialog(false);
      await fetchPolicyFiles();
    } catch (err) {
      setError(`${err}`);
    } finally {
      setSaving(false);
    }
  };

  const handleCloseNewDialog = () => {
    setShowNewDialog(false);
    setNewPolicyName('');
    setNewPolicyType('AccessGroupPolicy');
    setSelectedChildPolicies([]);
    setDenyReason('');
  };

  const toggleChildPolicy = (policyName: string) => {
    setSelectedChildPolicies(prev =>
      prev.includes(policyName)
        ? prev.filter(p => p !== policyName)
        : [...prev, policyName]
    );
  };

  // Check if current type is composite
  const isCompositeType = COMPOSITE_TYPES.includes(newPolicyType);
  const isSingleChildType = newPolicyType === 'NotPolicy';

  // Get existing policies that can be selected as children
  const availableChildPolicies = policyFiles.filter(p => !COMPOSITE_TYPES.includes(p.type));

  const handleEditorMount = useCallback(
    (editor: { addCommand: (keybinding: number, handler: () => void) => void }, monaco: { KeyMod: { CtrlCmd: number }; KeyCode: { KeyS: number } }) => {
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        handleSaveRef.current();
      });
    },
    []
  );

  const handleCloseEditor = (open: boolean) => {
    if (!open && hasUnsavedChanges) {
      setShowDiscardDialog(true);
      return;
    }
    setEditorOpen(open);
    if (!open) {
      setCurrentFile(null);
      setYamlContent('');
      setOriginalYaml('');
      setError(null);
    }
  };

  const handleDiscardConfirm = () => {
    setShowDiscardDialog(false);
    setEditorOpen(false);
    setCurrentFile(null);
    setYamlContent('');
    setOriginalYaml('');
    setError(null);
  };

  return (
    <div className="p-6 space-y-6">
      <SectionHeader
        title="Policies"
        badge={loading ? undefined : `${policyFiles.length}`}
        badgeColor="amber"
        action={
          <Button
            size="sm"
            onClick={() => setShowNewDialog(true)}
            className="h-7 text-xs"
          >
            <PlusIcon className="w-3.5 h-3.5 mr-1" />
            Add Policy
          </Button>
        }
      />

      {loading ? (
        <div className="flex items-center gap-3 py-8 justify-center text-muted-foreground">
          <div className="w-5 h-5 border-2 border-secondary border-t-primary rounded-full animate-spin" />
          <span className="text-sm">Loading policies...</span>
        </div>
      ) : policyFiles.length > 0 ? (
        <div className="space-y-2">
          {policyFiles.map((policy) => (
            <div
              key={policy.filename}
              className="p-3 rounded-lg bg-card/50 border border-border/50"
            >
              <div className="flex items-center gap-2">
                <ShieldIcon className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <span className="font-medium text-sm text-foreground flex-1 truncate">
                  {policy.name}
                </span>
                <span className={`px-2 py-0.5 rounded text-xs ${getPolicyTypeBadgeColor(policy.type)}`}>
                  {formatPolicyType(policy.type)}
                </span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => handleEdit(policy)}
                      className="p-1.5 text-muted-foreground hover:text-primary transition-colors rounded hover:bg-secondary/50"
                    >
                      <EditIcon className="w-4 h-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>Edit policy</p>
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => handleDeleteClick(policy)}
                      disabled={deleting === policy.filename}
                      className="p-1.5 text-muted-foreground hover:text-destructive transition-colors rounded hover:bg-secondary/50 disabled:opacity-50"
                    >
                      {deleting === policy.filename ? (
                        <span className="w-4 h-4 border border-muted-foreground border-t-foreground rounded-full animate-spin block" />
                      ) : (
                        <TrashIcon className="w-4 h-4" />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>Delete policy</p>
                  </TooltipContent>
                </Tooltip>
              </div>
              <p className="text-xs text-muted-foreground mt-1 ml-6">{policy.filename}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-8 text-center">
          <ShieldIcon className="w-10 h-10 mx-auto mb-3 text-secondary" />
          <p className="text-sm text-muted-foreground">No policies configured</p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            Click "Add Policy" to create a new policy file
          </p>
        </div>
      )}

      {/* New Policy Dialog */}
      {showNewDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-card rounded-lg p-5 w-[420px] border border-border max-h-[80vh] overflow-y-auto">
            <h3 className="text-base font-medium text-foreground mb-4">New Policy</h3>

            {/* Policy Name */}
            <div className="mb-4">
              <label className="block text-xs text-muted-foreground mb-1.5">Policy Name</label>
              <Input
                value={newPolicyName}
                onChange={(e) => setNewPolicyName(e.target.value)}
                placeholder="e.g., My Rate Limit"
                className="h-9"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !isCompositeType) handleCreate();
                  if (e.key === 'Escape') handleCloseNewDialog();
                }}
              />
            </div>

            {/* Policy Type */}
            <div className="mb-4">
              <label className="block text-xs text-muted-foreground mb-1.5">Policy Type</label>
              <Select
                value={newPolicyType}
                onValueChange={(value) => {
                  setNewPolicyType(value);
                  setSelectedChildPolicies([]);
                }}
              >
                <SelectTrigger className="w-full h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel>Policy Type</SelectLabel>
                    {POLICY_TYPES.map((pt) => (
                      <SelectItem key={pt.value} value={pt.value}>
                        {pt.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1.5">
                {POLICY_TYPES.find(pt => pt.value === newPolicyType)?.description}
              </p>
            </div>

            {/* Child Policy Selection (for composite types) */}
            {isCompositeType && (
              <div className="mb-4">
                <label className="block text-xs text-muted-foreground mb-1.5">
                  {isSingleChildType ? 'Select Policy to Negate' : 'Select Child Policies'}
                </label>
                {availableChildPolicies.length > 0 ? (
                  <div className="max-h-40 overflow-y-auto border border-border rounded-md bg-background">
                    {availableChildPolicies.map((policy) => (
                      <label
                        key={policy.filename}
                        className="flex items-center gap-2 px-3 py-2 hover:bg-card/50 cursor-pointer border-b border-border/50 last:border-b-0"
                      >
                        <input
                          type={isSingleChildType ? 'radio' : 'checkbox'}
                          name="childPolicy"
                          checked={selectedChildPolicies.includes(policy.name)}
                          onChange={() => {
                            if (isSingleChildType) {
                              setSelectedChildPolicies([policy.name]);
                            } else {
                              toggleChildPolicy(policy.name);
                            }
                          }}
                          className="w-4 h-4 accent-primary"
                        />
                        <span className="text-sm text-foreground flex-1">{policy.name}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] ${getPolicyTypeBadgeColor(policy.type)}`}>
                          {formatPolicyType(policy.type)}
                        </span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="p-3 border border-border rounded-md bg-background text-center">
                    <p className="text-xs text-muted-foreground">No policies available</p>
                    <p className="text-xs text-muted-foreground/70 mt-1">
                      Create non-composite policies first
                    </p>
                  </div>
                )}
                {!isSingleChildType && selectedChildPolicies.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1.5">
                    Selected: {selectedChildPolicies.join(', ')}
                  </p>
                )}
              </div>
            )}

            {/* Deny Reason (for NotPolicy) */}
            {newPolicyType === 'NotPolicy' && (
              <div className="mb-4">
                <label className="block text-xs text-muted-foreground mb-1.5">Deny Reason (optional)</label>
                <Input
                  value={denyReason}
                  onChange={(e) => setDenyReason(e.target.value)}
                  placeholder="Access denied by policy negation"
                  className="h-9"
                />
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2 mt-5 pt-4 border-t border-border/50">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCloseNewDialog}
                className="h-8"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleCreate}
                disabled={saving || !newPolicyName.trim()}
                className="h-8"
              >
                {saving ? 'Creating...' : 'Create Policy'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* YAML Editor Sheet */}
      <Sheet open={editorOpen} onOpenChange={handleCloseEditor}>
        <SheetContent side="right" className="w-[600px] sm:max-w-[600px] p-0 flex flex-col">
          <SheetHeader className="px-4 py-3 border-b border-border/50 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SheetTitle className="text-base">{currentFile?.filename || 'Policy'}</SheetTitle>
                {hasUnsavedChanges && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="w-2 h-2 rounded-full bg-chart-3" />
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      <p>Unsaved changes</p>
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSave}
                  disabled={saving || !hasUnsavedChanges}
                  className="h-7 text-xs"
                >
                  {saving ? (
                    <>
                      <span className="w-3 h-3 border border-muted-foreground border-t-transparent rounded-full animate-spin mr-1.5" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <SaveIcon className="w-3.5 h-3.5 mr-1.5" />
                      Save
                    </>
                  )}
                </Button>
              </div>
            </div>
          </SheetHeader>

          {/* Error message */}
          {error && (
            <div className="mx-4 mt-3 p-3 bg-destructive/10 border border-destructive/30 rounded-lg text-sm text-destructive flex-shrink-0">
              {error}
            </div>
          )}

          {/* Monaco Editor */}
          <div className="flex-1 overflow-hidden">
            <Editor
              height="100%"
              language="yaml"
              theme="vs-dark"
              value={yamlContent}
              onChange={handleEditorChange}
              onMount={handleEditorMount}
              loading={
                <div className="h-full flex items-center justify-center bg-background text-muted-foreground">
                  <div className="text-center">
                    <div className="w-8 h-8 border-2 border-secondary border-t-primary rounded-full animate-spin mx-auto mb-3" />
                    <p className="text-sm">Loading editor...</p>
                  </div>
                </div>
              }
              options={{
                fontSize: 13,
                fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                padding: { top: 16, bottom: 16 },
                lineNumbers: 'on',
                glyphMargin: false,
                folding: true,
                lineDecorationsWidth: 10,
                lineNumbersMinChars: 3,
                renderLineHighlight: 'line',
                scrollbar: {
                  vertical: 'auto',
                  horizontal: 'auto',
                  verticalScrollbarSize: 8,
                  horizontalScrollbarSize: 8,
                },
                automaticLayout: true,
                wordWrap: 'on',
                tabSize: 2,
                insertSpaces: true,
              }}
            />
          </div>

          {/* Status bar */}
          <div className="flex-shrink-0 px-4 py-1.5 border-t border-border/50 bg-card/30 text-xs text-muted-foreground flex items-center justify-between">
            <span>YAML</span>
            <span className="text-muted-foreground/70">Ctrl+S to save</span>
          </div>
        </SheetContent>
      </Sheet>

      {/* Delete Policy Confirmation Dialog */}
      <AlertDialog open={!!policyToDelete} onOpenChange={(open) => !open && setPolicyToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader className="items-center">
            <AlertDialogTitle>
              <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10">
                <OctagonAlert className="h-7 w-7 text-destructive" />
              </div>
              Delete Policy
            </AlertDialogTitle>
            <AlertDialogDescription className="text-center text-[15px]">
              Are you sure you want to delete "{policyToDelete?.name}"? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="mt-2 sm:justify-center">
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDeleteConfirm}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Discard Changes Confirmation Dialog */}
      <AlertDialog open={showDiscardDialog} onOpenChange={setShowDiscardDialog}>
        <AlertDialogContent>
          <AlertDialogHeader className="items-center">
            <AlertDialogTitle>
              <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-chart-3/10">
                <TriangleAlert className="h-7 w-7 text-chart-3" />
              </div>
              Unsaved Changes
            </AlertDialogTitle>
            <AlertDialogDescription className="text-center text-[15px]">
              You have unsaved changes. Are you sure you want to discard them?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="mt-2 sm:justify-center">
            <AlertDialogCancel>Keep Editing</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDiscardConfirm}>
              Discard
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// Edit icon
function EditIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
    </svg>
  );
}

// Save icon
function SaveIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
    </svg>
  );
}

// ============================================================================
// SHARED COMPONENTS
// ============================================================================
function SectionHeader({
  title,
  badge,
  badgeColor = 'slate',
  action,
}: {
  title: string;
  badge?: string;
  badgeColor?: 'slate' | 'amber';
  action?: React.ReactNode;
}) {
  const colors = {
    slate: 'bg-secondary text-secondary-foreground',
    amber: 'bg-chart-3/20 text-chart-3',
  };

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-medium text-foreground">{title}</h2>
        {badge && (
          <span className={`px-2 py-0.5 rounded text-xs ${colors[badgeColor]}`}>
            {badge}
          </span>
        )}
      </div>
      {action}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}

// ============================================================================
// ICONS
// ============================================================================
function FolderIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
    </svg>
  );
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  );
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}

function PackageIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
    </svg>
  );
}

function ShieldIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  );
}
