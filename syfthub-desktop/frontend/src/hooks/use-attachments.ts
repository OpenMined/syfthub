import { useCallback, useEffect, useState } from 'react';
import {
  AttachToActiveSession,
  SaveAttachmentAs,
  AttachmentInlineBytes,
  ValidateAttachmentPath,
} from '../../wailsjs/go/main/App';
import { EventsOn } from '../../wailsjs/runtime/runtime';

// PendingAttachment is a queued, pre-validated host path. The validation
// runs at queue time (size/type/exists) so the user learns about a bad path
// at drop time, not when the session starts.
export interface PendingAttachment {
  host_path: string;
  name: string;
  mime: string;
  size_bytes: number;
}

// AttachmentSummary mirrors the Go struct returned by AttachToActiveSession.
// The bytes live on the host's side of the tunnel — no local_path exists on
// the client. `delivered` flips true when the host's user.attachment ack
// event arrives, so the chip can show a "✓" once the file is materialized
// on the host.
export interface AttachmentSummary {
  file_id: string;
  name: string;
  mime: string;
  size_bytes: number;
  sha256: string;
  delivered?: boolean;
}

// Per-file inbound download progress, populated from attachment.progress events.
export interface AttachmentProgress {
  downloaded: number;
  total: number;
}

/**
 * useAttachments tracks the list of files the user has staged for the
 * currently-running agent session AND the inbound-download progress map.
 *
 * Flow:
 *  1. User drops a file before a session is live → stagePath(hostPath); chip
 *     renders with a "queued" badge.
 *  2. Session starts → flushPending() uploads each queued path via the Wails
 *     binding, which streams the bytes to the host. Files ≤ 64 KiB ride
 *     inline; larger files spill to NATS Object Store via the SDK.
 *  3. Host emits user.attachment ack → chip flips to delivered ✓.
 *  4. Saving an agent-emitted attachment via SaveAttachmentAs streams via the
 *     SDK and emits attachment.progress events, which populate the progress
 *     map keyed by file_id.
 *
 * See docs/architecture/attachments.md.
 */
export function useAttachments() {
  const [staged, setStaged] = useState<AttachmentSummary[]>([]);
  // pending holds pre-validated descriptors of host paths queued before a
  // session was live. Validation (exists, not a directory, within
  // MaxAttachmentBytes) runs at stage time so the user gets immediate
  // feedback rather than discovering a 5 GiB drop only at session start.
  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const [progress, setProgress] = useState<Record<string, AttachmentProgress>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Subscribe to the host-emitted attachment events.
  useEffect(() => {
    const unsubscribe = EventsOn(
      'agent:event',
      (event: { type: string; data?: Record<string, unknown> }) => {
        if (event.type === 'user.attachment') {
          const fileId = String(event.data?.file_id ?? '');
          if (!fileId) return;
          setStaged(prev =>
            prev.map(s => (s.file_id === fileId ? { ...s, delivered: true } : s)),
          );
        } else if (event.type === 'attachment.progress') {
          const fileId = String(event.data?.file_id ?? '');
          if (!fileId) return;
          const downloaded = Number(event.data?.downloaded ?? 0);
          const total = Number(event.data?.total ?? 0);
          setProgress(prev => ({
            ...prev,
            [fileId]: { downloaded, total },
          }));
        }
      },
    );
    return () => {
      unsubscribe();
    };
  }, []);

  const attach = useCallback(async (hostPath: string) => {
    setBusy(true);
    setError(null);
    try {
      const summary = await AttachToActiveSession(hostPath);
      setStaged(prev => [...prev, summary]);
      return summary;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      throw e;
    } finally {
      setBusy(false);
    }
  }, []);

  // stagePath validates the host path (exists, regular file, within the
  // size cap) BEFORE queuing it. Returns the resolved descriptor on success
  // so the caller can render a real chip; throws on rejection so the UI
  // surfaces the failure at drop time instead of at session start.
  const stagePath = useCallback(async (hostPath: string): Promise<PendingAttachment> => {
    setError(null);
    try {
      const summary = await ValidateAttachmentPath(hostPath);
      const entry: PendingAttachment = {
        host_path: hostPath,
        name: summary.name,
        mime: summary.mime,
        size_bytes: summary.size_bytes,
      };
      setPending(prev => [...prev, entry]);
      return entry;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      throw e;
    }
  }, []);

  // flushPending promotes every queued path to a real attachment by calling
  // attach() for each. Per-path failures are recorded in `error` but do not
  // abort the loop. Returns the count successfully uploaded.
  const flushPending = useCallback(async () => {
    let snapshot: PendingAttachment[] = [];
    setPending(prev => {
      snapshot = prev;
      return [];
    });
    if (snapshot.length === 0) return 0;
    let count = 0;
    for (const p of snapshot) {
      try {
        await attach(p.host_path);
        count++;
      } catch {
        /* attach() records the error; keep iterating */
      }
    }
    return count;
  }, [attach]);

  const removePending = useCallback((hostPath: string) => {
    setPending(prev => prev.filter(p => p.host_path !== hostPath));
  }, []);

  // saveAs opens the native save-as dialog and writes the attachment to the
  // chosen path. Returns the absolute destination on success, null on user
  // cancel, throws on failure.
  const saveAs = useCallback(
    async (fileId: string, suggestedName: string): Promise<string | null> => {
      const dest = await SaveAttachmentAs(fileId, suggestedName);
      return dest || null;
    },
    [],
  );

  const inlineBytes = useCallback(async (fileId: string, maxBytes = 0) => {
    return AttachmentInlineBytes(fileId, maxBytes);
  }, []);

  const remove = useCallback((fileId: string) => {
    setStaged(prev => prev.filter(s => s.file_id !== fileId));
  }, []);

  const clear = useCallback(() => {
    setStaged([]);
    setProgress({});
  }, []);

  return {
    staged,
    pending,
    progress,
    attach,
    stagePath,
    flushPending,
    removePending,
    saveAs,
    inlineBytes,
    remove,
    clear,
    busy,
    error,
  };
}
