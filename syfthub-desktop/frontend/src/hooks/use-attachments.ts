import { useCallback, useState } from 'react';
import {
  AttachToActiveSession,
  DownloadActiveSessionAttachment,
  AttachmentInlineBytes,
} from '../../wailsjs/go/main/App';

// AttachmentSummary mirrors the Go struct returned by AttachToActiveSession.
export interface AttachmentSummary {
  file_id: string;
  name: string;
  mime: string;
  size_bytes: number;
  sha256: string;
  local_path: string;
}

/**
 * useAttachments tracks the list of files the user has staged for the
 * currently-running agent session. Each staged file is materialized into the
 * session's AttachmentDir via AttachToActiveSession (Wails binding).
 *
 * See docs/architecture/attachments.md.
 */
export function useAttachments() {
  const [staged, setStaged] = useState<AttachmentSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const download = useCallback(async (fileId: string, destPath: string) => {
    setBusy(true);
    setError(null);
    try {
      await DownloadActiveSessionAttachment(fileId, destPath);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      throw e;
    } finally {
      setBusy(false);
    }
  }, []);

  const inlineBytes = useCallback(async (fileId: string, maxBytes = 0) => {
    return AttachmentInlineBytes(fileId, maxBytes);
  }, []);

  const remove = useCallback((fileId: string) => {
    setStaged(prev => prev.filter(s => s.file_id !== fileId));
  }, []);

  const clear = useCallback(() => {
    setStaged([]);
  }, []);

  return { staged, attach, download, inlineBytes, remove, clear, busy, error };
}
