import { useEffect, useRef, useState } from 'react';
import {
  Download,
  ExternalLink,
  File as FileIcon,
  FileCode,
  FileImage,
  FileText,
  Loader2,
  X,
} from 'lucide-react';
import {
  AttachmentInlineBytes,
  OpenInDefaultApp,
} from '../../../wailsjs/go/main/App';

export interface AttachmentChipProps {
  fileId: string;
  name: string;
  mime: string;
  sizeBytes: number;
  /**
   * staged=true means the user uploaded this file (chip strip, with remove
   * action). staged=false / undefined means the agent emitted it (timeline
   * entry, with download action + image figure for image MIMEs).
   */
  staged?: boolean;
  onRemove?: (fileId: string) => void;
  /**
   * Save the attachment somewhere on the user's disk. The parent should
   * resolve with the absolute destination path on success (used to
   * tooltip the "Saved" confirmation), null/undefined on user cancel,
   * or throw on failure (chip shows the error briefly).
   */
  onDownload?: (fileId: string) => Promise<string | null | undefined>;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function humanSize(bytes: number): string {
  const units = [
    ['GB', 1024 ** 3],
    ['MB', 1024 ** 2],
    ['KB', 1024],
  ] as const;
  for (const [unit, div] of units) {
    const d = div as number;
    if (bytes >= d) {
      const n = bytes / d;
      // 1.4 MB but 12 MB — drop the decimal once we're past 10.
      return `${n >= 10 ? Math.round(n) : n.toFixed(1)} ${unit}`;
    }
  }
  return `${bytes} B`;
}

function iconForMime(mime: string) {
  if (mime.startsWith('image/')) return FileImage;
  if (mime.startsWith('text/')) return FileText;
  if (mime === 'application/pdf') return FileText;
  if (
    mime.includes('json') ||
    mime.includes('javascript') ||
    mime.includes('typescript') ||
    mime.includes('xml') ||
    mime.includes('html') ||
    mime.includes('css')
  )
    return FileCode;
  return FileIcon;
}

// Load decrypted bytes via Wails and return a same-MIME blob URL the caller
// can use as <img src>. Caps the fetch to maxBytes to avoid pulling huge
// images into memory for a thumbnail.
function useInlinePreview(
  fileId: string,
  mime: string,
  enabled: boolean,
  maxBytes: number,
): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setUrl(null);
      return;
    }
    let revoked = false;
    let created: string | null = null;
    (async () => {
      try {
        const bytes = await AttachmentInlineBytes(fileId, maxBytes);
        if (revoked) return;
        const u8 = new Uint8Array(bytes as ArrayLike<number>);
        const blob = new Blob([u8], { type: mime });
        created = URL.createObjectURL(blob);
        setUrl(created);
      } catch {
        /* preview unavailable; chip falls back to the icon variant */
      }
    })();
    return () => {
      revoked = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [enabled, fileId, mime, maxBytes]);

  return url;
}

// ── Download/Open button ──────────────────────────────────────────────────

type DownloadState =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'saved'; path: string }
  | { kind: 'error' };

/**
 * DownloadOrOpenButton flips role based on saved state.
 *
 *   idle    -> Download icon, neutral foreground. Click = save to Downloads.
 *   saving  -> Loader spinner, disabled.
 *   saved   -> ExternalLink icon, primary foreground. Click = open the
 *              saved file in the OS's default app. Tooltip shows the
 *              absolute path. State is sticky for the session.
 *   error   -> Download icon, destructive foreground, for ~2.5s, reverts.
 *
 * State lives here AND is reported up via onStateChange so the parent
 * chip can tint its background to match.
 */
function DownloadOrOpenButton({
  fileId,
  name,
  onDownload,
  size,
  state,
  setState,
}: {
  fileId: string;
  name: string;
  onDownload: (fileId: string) => Promise<string | null | undefined>;
  size: 'sm' | 'md';
  state: DownloadState;
  setState: (s: DownloadState) => void;
}) {
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  const cls = size === 'md' ? 'h-6 w-6' : 'h-5 w-5';
  const iconCls = size === 'md' ? 'h-3.5 w-3.5' : 'h-3 w-3';

  const handleClick = async () => {
    if (state.kind === 'saving') return;
    // Saved path is sticky — clicking again opens the file in the default app.
    if (state.kind === 'saved') {
      try {
        await OpenInDefaultApp(state.path);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('open in default app failed', err);
      }
      return;
    }
    setState({ kind: 'saving' });
    try {
      const dest = await onDownload(fileId);
      if (!dest) {
        setState({ kind: 'idle' });
        return;
      }
      setState({ kind: 'saved', path: dest });
    } catch (err) {
      setState({ kind: 'error' });
      // eslint-disable-next-line no-console
      console.error('download failed', err);
      timerRef.current = window.setTimeout(
        () => setState({ kind: 'idle' }),
        2500,
      );
    }
  };

  const tooltip =
    state.kind === 'saved'
      ? `Open ${name}  ·  ${state.path}`
      : state.kind === 'error'
        ? 'Save failed — see console'
        : state.kind === 'saving'
          ? 'Saving…'
          : `Save ${name} to Downloads`;

  let Icon = Download;
  if (state.kind === 'saving') Icon = Loader2;
  else if (state.kind === 'saved') Icon = ExternalLink;

  return (
    <button
      type='button'
      onClick={handleClick}
      disabled={state.kind === 'saving'}
      className={`${cls} focus-visible:ring-ring focus-visible:ring-offset-background ml-0.5 flex shrink-0 items-center justify-center rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50 ${
        state.kind === 'saved'
          ? 'text-primary-foreground hover:bg-primary-foreground/15'
          : state.kind === 'error'
            ? 'text-destructive hover:bg-background'
            : 'text-muted-foreground hover:text-foreground hover:bg-background'
      }`}
      aria-label={tooltip}
      title={tooltip}
    >
      <Icon
        className={`${iconCls} ${state.kind === 'saving' ? 'animate-spin' : ''}`}
        aria-hidden='true'
      />
    </button>
  );
}

// ── Component ─────────────────────────────────────────────────────────────

/**
 * AttachmentChip renders a single attachment in two variants:
 *
 *  - **Compact chip** (default) — pill with a MIME-aware icon, filename,
 *    size, and a hover-revealed action button (remove for staged, download
 *    for agent-emitted). Image MIMEs show a 20×20 thumbnail in place of
 *    the icon. Used for both the staged-files strip above the input and
 *    inline agent-emitted non-image files in the timeline.
 *
 *  - **Image figure** — only for agent-emitted attachments with image
 *    MIMEs. Renders a bordered card with the decrypted image (max 360px
 *    wide), filename + size below, and a download icon.
 */
export function AttachmentChip({
  fileId,
  name,
  mime,
  sizeBytes,
  staged,
  onRemove,
  onDownload,
}: AttachmentChipProps) {
  const isImage = mime.startsWith('image/');

  // Image figure variant: only for agent-emitted attachments. Cap fetch at
  // 4 MiB so we don't accidentally pull a 20 MB PNG into memory.
  const wantsFigure = isImage && !staged;
  const figureUrl = useInlinePreview(fileId, mime, wantsFigure, 4 * 1024 * 1024);

  // Tiny thumbnail for staged image chips (20×20). Cap fetch at 256 KiB
  // — we only need enough for a thumb-quality decode.
  const wantsThumb = isImage && Boolean(staged);
  const thumbUrl = useInlinePreview(fileId, mime, wantsThumb, 256 * 1024);

  // Download/open state lives at the chip level so the chip background can
  // tint to match. Only meaningful for agent-emitted attachments
  // (staged === false || undefined). Stays sticky for the session once saved.
  const [downloadState, setDownloadState] = useState<DownloadState>({
    kind: 'idle',
  });
  const isSaved = downloadState.kind === 'saved';

  // ── Image figure ──
  if (wantsFigure) {
    return (
      <figure
        className={`animate-in fade-in slide-in-from-bottom-1 my-2 inline-flex max-w-md flex-col overflow-hidden rounded-xl border duration-200 transition-colors ${
          isSaved
            ? 'border-primary/40 bg-primary/10'
            : 'border-border bg-muted/30'
        }`}
      >
        {figureUrl ? (
          <img
            src={figureUrl}
            alt={name}
            className='block max-h-80 w-auto max-w-full'
          />
        ) : (
          <div className='bg-muted/50 flex h-32 items-center justify-center'>
            <FileImage className='text-muted-foreground h-6 w-6' />
          </div>
        )}
        <figcaption
          className={`flex items-center justify-between gap-3 px-3 py-2 transition-colors ${
            isSaved ? 'bg-primary/15' : ''
          }`}
        >
          <div className='min-w-0 flex-1'>
            <p
              className={`truncate text-xs font-medium ${
                isSaved ? 'text-primary-foreground' : 'text-foreground'
              }`}
            >
              {name}
            </p>
            <p
              className={`text-[10px] tabular-nums ${
                isSaved
                  ? 'text-primary-foreground/70'
                  : 'text-muted-foreground'
              }`}
            >
              {humanSize(sizeBytes)} · {mime.split('/')[1] ?? mime}
              {isSaved && ' · Saved'}
            </p>
          </div>
          {onDownload && (
            <DownloadOrOpenButton
              fileId={fileId}
              name={name}
              onDownload={onDownload}
              size='md'
              state={downloadState}
              setState={setDownloadState}
            />
          )}
        </figcaption>
      </figure>
    );
  }

  // ── Compact chip ──
  const Icon = iconForMime(mime);
  const showThumbnail = Boolean(thumbUrl && staged);

  return (
    <span
      className={`group/chip animate-in fade-in slide-in-from-bottom-1 inline-flex max-w-[18rem] items-center gap-2 rounded-md border py-1 pl-2 pr-1 text-xs duration-150 transition-colors ${
        isSaved
          ? 'border-primary/40 bg-primary text-primary-foreground'
          : 'border-border bg-muted text-foreground'
      }`}
      title={`${name} · ${mime}`}
    >
      {showThumbnail ? (
        <img
          src={thumbUrl!}
          alt=''
          aria-hidden='true'
          className='border-border h-5 w-5 shrink-0 rounded border object-cover'
        />
      ) : (
        <Icon
          className={`h-3.5 w-3.5 shrink-0 ${
            isSaved ? 'text-primary-foreground/80' : 'text-muted-foreground'
          }`}
          aria-hidden='true'
        />
      )}
      <span className='min-w-0 truncate'>{name}</span>
      <span
        className={`shrink-0 text-[10px] tabular-nums ${
          isSaved ? 'text-primary-foreground/70' : 'text-muted-foreground'
        }`}
      >
        {humanSize(sizeBytes)}
      </span>
      {staged && onRemove && (
        <button
          type='button'
          onClick={() => onRemove(fileId)}
          className='text-muted-foreground hover:text-foreground hover:bg-background focus-visible:ring-ring focus-visible:ring-offset-background ml-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2'
          aria-label={`Remove ${name}`}
        >
          <X className='h-3 w-3' aria-hidden='true' />
        </button>
      )}
      {!staged && onDownload && (
        <DownloadOrOpenButton
          fileId={fileId}
          name={name}
          onDownload={onDownload}
          size='sm'
          state={downloadState}
          setState={setDownloadState}
        />
      )}
    </span>
  );
}
