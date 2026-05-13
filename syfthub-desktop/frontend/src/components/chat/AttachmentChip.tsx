import { useEffect, useState } from 'react';
import {
  Download,
  File as FileIcon,
  FileCode,
  FileImage,
  FileText,
  X,
} from 'lucide-react';
import { AttachmentInlineBytes } from '../../../wailsjs/go/main/App';

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
  onDownload?: (fileId: string) => void;
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

  // ── Image figure ──
  if (wantsFigure) {
    return (
      <figure className='border-border bg-muted/30 animate-in fade-in slide-in-from-bottom-1 my-2 inline-flex max-w-md flex-col overflow-hidden rounded-xl border duration-200'>
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
        <figcaption className='flex items-center justify-between gap-3 px-3 py-2'>
          <div className='min-w-0 flex-1'>
            <p className='text-foreground truncate text-xs font-medium'>
              {name}
            </p>
            <p className='text-muted-foreground text-[10px] tabular-nums'>
              {humanSize(sizeBytes)} · {mime.split('/')[1] ?? mime}
            </p>
          </div>
          {onDownload && (
            <button
              type='button'
              onClick={() => onDownload(fileId)}
              className='text-muted-foreground hover:text-foreground focus-visible:ring-ring focus-visible:ring-offset-background flex h-6 w-6 shrink-0 items-center justify-center rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2'
              aria-label={`Download ${name}`}
            >
              <Download className='h-3.5 w-3.5' aria-hidden='true' />
            </button>
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
      className='group/chip border-border bg-muted text-foreground animate-in fade-in slide-in-from-bottom-1 inline-flex max-w-[18rem] items-center gap-2 rounded-md border py-1 pl-2 pr-1 text-xs duration-150'
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
          className='text-muted-foreground h-3.5 w-3.5 shrink-0'
          aria-hidden='true'
        />
      )}
      <span className='min-w-0 truncate'>{name}</span>
      <span className='text-muted-foreground shrink-0 text-[10px] tabular-nums'>
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
        <button
          type='button'
          onClick={() => onDownload(fileId)}
          className='text-muted-foreground hover:text-foreground hover:bg-background focus-visible:ring-ring focus-visible:ring-offset-background ml-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2'
          aria-label={`Download ${name}`}
        >
          <Download className='h-3 w-3' aria-hidden='true' />
        </button>
      )}
    </span>
  );
}
