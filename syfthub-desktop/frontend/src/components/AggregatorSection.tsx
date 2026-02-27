import { useEffect, useState } from 'react';
import { Loader2, Plus, Star, Trash2, Edit2, Server, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useAppStore } from '@/stores/appStore';
import {
  GetUserAggregators,
  CreateUserAggregator,
  UpdateUserAggregator,
  DeleteUserAggregator,
  SetDefaultUserAggregator,
} from '../../wailsjs/go/main/App';
import { main } from '../../wailsjs/go/models';

type UserAggregator = main.UserAggregator;

// ============================================================================
// Validation helpers
// ============================================================================

function validateUrl(url: string): string | null {
  if (!url.trim()) return 'URL is required';
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return 'URL must use http:// or https://';
    }
    return null;
  } catch {
    return 'Please enter a valid URL';
  }
}

function validateName(name: string): string | null {
  if (!name.trim()) return 'Name is required';
  if (name.trim().length > 100) return 'Name must be 100 characters or fewer';
  return null;
}

// ============================================================================
// Inline form (add / edit)
// ============================================================================

interface AggregatorFormProps {
  initialName?: string;
  initialUrl?: string;
  showDefaultCheckbox?: boolean;
  isSubmitting: boolean;
  submitLabel: string;
  onSubmit: (name: string, url: string, isDefault: boolean) => void;
  onCancel: () => void;
}

function AggregatorForm({
  initialName = '',
  initialUrl = '',
  showDefaultCheckbox = false,
  isSubmitting,
  submitLabel,
  onSubmit,
  onCancel,
}: AggregatorFormProps) {
  const [name, setName] = useState(initialName);
  const [url, setUrl] = useState(initialUrl);
  const [isDefault, setIsDefault] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);

  const handleSubmit = () => {
    const ne = validateName(name);
    const ue = validateUrl(url);
    setNameError(ne);
    setUrlError(ue);
    if (ne || ue) return;
    onSubmit(name.trim(), url.trim(), isDefault);
  };

  return (
    <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
      {/* Name */}
      <div className="space-y-1">
        <Label htmlFor="agg-name" className="text-xs">
          Name
        </Label>
        <Input
          id="agg-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My Aggregator"
          className={`h-8 text-sm ${nameError ? 'border-destructive' : ''}`}
          disabled={isSubmitting}
        />
        {nameError && <p className="text-xs text-destructive">{nameError}</p>}
      </div>

      {/* URL */}
      <div className="space-y-1">
        <Label htmlFor="agg-url" className="text-xs">
          URL
        </Label>
        <Input
          id="agg-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://aggregator.example.com"
          className={`h-8 text-sm ${urlError ? 'border-destructive' : ''}`}
          disabled={isSubmitting}
        />
        {urlError && <p className="text-xs text-destructive">{urlError}</p>}
      </div>

      {/* Default checkbox (only for add form) */}
      {showDefaultCheckbox && (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="agg-default"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            disabled={isSubmitting}
            className="h-3.5 w-3.5"
          />
          <Label htmlFor="agg-default" className="text-xs font-normal cursor-pointer">
            Set as default
          </Label>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel} disabled={isSubmitting} className="h-7 text-xs">
          Cancel
        </Button>
        <Button size="sm" onClick={handleSubmit} disabled={isSubmitting} className="h-7 text-xs">
          {isSubmitting ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}

// ============================================================================
// Single aggregator card
// ============================================================================

interface AggregatorCardProps {
  aggregator: UserAggregator;
  isProcessing: boolean;
  onEdit: (aggregator: UserAggregator) => void;
  onSetDefault: (id: number) => void;
  onDelete: (id: number) => void;
}

function AggregatorCard({ aggregator, isProcessing, onEdit, onSetDefault, onDelete }: AggregatorCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const truncateUrl = (url: string) => {
    try {
      const u = new URL(url);
      const display = u.host + (u.pathname !== '/' ? u.pathname : '');
      return display.length > 45 ? display.slice(0, 44) + '…' : display;
    } catch {
      return url.length > 45 ? url.slice(0, 44) + '…' : url;
    }
  };

  return (
    <div className="rounded-md border border-border bg-card p-3 space-y-2">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Server className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <span className="text-sm font-medium truncate">{aggregator.name}</span>
          {aggregator.is_default && (
            <Badge variant="secondary" className="text-xs h-4 px-1.5 shrink-0">
              default
            </Badge>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {!aggregator.is_default && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              title="Set as default"
              disabled={isProcessing}
              onClick={() => onSetDefault(aggregator.id)}
            >
              <Star className="w-3.5 h-3.5" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            title="Edit"
            disabled={isProcessing}
            onClick={() => onEdit(aggregator)}
          >
            <Edit2 className="w-3.5 h-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-destructive hover:text-destructive"
            title="Delete"
            disabled={isProcessing}
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* URL */}
      <p className="text-xs text-muted-foreground font-mono" title={aggregator.url}>
        {truncateUrl(aggregator.url)}
      </p>

      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="flex items-center justify-between gap-2 rounded border border-destructive/40 bg-destructive/5 px-2 py-1.5">
          <span className="text-xs text-destructive">Delete this aggregator?</span>
          <div className="flex gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-xs"
              onClick={() => setConfirmDelete(false)}
              disabled={isProcessing}
            >
              No
            </Button>
            <Button
              variant="destructive"
              size="sm"
              className="h-6 text-xs"
              onClick={() => {
                setConfirmDelete(false);
                onDelete(aggregator.id);
              }}
              disabled={isProcessing}
            >
              Yes, delete
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// AggregatorSection — main export
// ============================================================================

interface AggregatorSectionProps {
  isConfigured: boolean;
}

export function AggregatorSection({ isConfigured }: AggregatorSectionProps) {
  const refreshAggregatorURL = useAppStore((s) => s.refreshAggregatorURL);

  const [aggregators, setAggregators] = useState<UserAggregator[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  // Add form
  const [showAddForm, setShowAddForm] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  // Edit form
  const [editingAggregator, setEditingAggregator] = useState<UserAggregator | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  const fetchAggregators = async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await GetUserAggregators();
      setAggregators(list ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isConfigured) {
      fetchAggregators();
    }
  }, [isConfigured]);

  if (!isConfigured) return null;

  // ---- handlers ----

  const handleAdd = async (name: string, url: string, isDefault: boolean) => {
    setIsAdding(true);
    setError(null);
    try {
      await CreateUserAggregator(name, url, isDefault);
      setShowAddForm(false);
      await fetchAggregators();
      await refreshAggregatorURL();
    } catch (err) {
      setError(String(err));
    } finally {
      setIsAdding(false);
    }
  };

  const handleEdit = async (name: string, url: string, _isDefault: boolean) => {
    if (!editingAggregator) return;
    setIsEditing(true);
    setError(null);
    try {
      await UpdateUserAggregator(editingAggregator.id, name, url);
      setEditingAggregator(null);
      await fetchAggregators();
      await refreshAggregatorURL();
    } catch (err) {
      setError(String(err));
    } finally {
      setIsEditing(false);
    }
  };

  const handleSetDefault = async (id: number) => {
    setProcessing(true);
    setError(null);
    try {
      await SetDefaultUserAggregator(id);
      await fetchAggregators();
      await refreshAggregatorURL();
    } catch (err) {
      setError(String(err));
    } finally {
      setProcessing(false);
    }
  };

  const handleDelete = async (id: number) => {
    setProcessing(true);
    setError(null);
    try {
      await DeleteUserAggregator(id);
      await fetchAggregators();
      await refreshAggregatorURL();
    } catch (err) {
      setError(String(err));
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-foreground">Aggregators</span>
        {!showAddForm && !editingAggregator && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => setShowAddForm(true)}
            disabled={loading || processing}
          >
            <Plus className="w-3 h-3" />
            Add
          </Button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2 rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2 text-destructive text-xs">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Add form */}
      {showAddForm && (
        <AggregatorForm
          showDefaultCheckbox
          isSubmitting={isAdding}
          submitLabel="Add Aggregator"
          onSubmit={handleAdd}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Loading aggregators…
        </div>
      )}

      {/* Aggregator list */}
      {!loading && aggregators.length === 0 && !showAddForm && (
        <p className="text-xs text-muted-foreground">
          No aggregators configured. Add one to enable chat.
        </p>
      )}

      {!loading && aggregators.map((agg) => (
        <div key={agg.id}>
          {editingAggregator?.id === agg.id ? (
            <AggregatorForm
              initialName={agg.name}
              initialUrl={agg.url}
              isSubmitting={isEditing}
              submitLabel="Save Changes"
              onSubmit={handleEdit}
              onCancel={() => setEditingAggregator(null)}
            />
          ) : (
            <AggregatorCard
              aggregator={agg}
              isProcessing={processing}
              onEdit={(a) => setEditingAggregator(a)}
              onSetDefault={handleSetDefault}
              onDelete={handleDelete}
            />
          )}
        </div>
      ))}
    </div>
  );
}
