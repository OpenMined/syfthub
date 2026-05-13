import { useEffect, useState } from 'react';
import { AttachmentInlineBytes } from '../../../wailsjs/go/main/App';

export interface AttachmentChipProps {
  fileId: string;
  name: string;
  mime: string;
  sizeBytes: number;
  // If true, render a download "x" chip; if image MIME, render an inline preview.
  // staged=true means the user staged this for upload (rendered with a remove "x");
  // staged=false means the agent emitted it (rendered with a download icon).
  staged?: boolean;
  onRemove?: (fileId: string) => void;
  onDownload?: (fileId: string) => void;
}

const HUMAN_SIZES = [
  [1024 ** 3, 'GiB'],
  [1024 ** 2, 'MiB'],
  [1024, 'KiB'],
] as const;

function humanSize(bytes: number): string {
  for (const [div, unit] of HUMAN_SIZES) {
    if (bytes >= (div as number)) {
      return `${(bytes / (div as number)).toFixed(1)} ${unit}`;
    }
  }
  return `${bytes} B`;
}

/**
 * AttachmentChip renders a paperclip-style chip for an attachment. For image
 * MIMEs it inlines a preview by fetching plaintext bytes via Wails. For
 * everything else it shows a filename + size with a remove/download action.
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
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!mime.startsWith('image/')) return;
    let revoked = false;
    let createdUrl: string | null = null;
    (async () => {
      try {
        // Cap preview fetch at 2 MiB to avoid loading huge images into memory.
        const bytes = await AttachmentInlineBytes(fileId, 2 * 1024 * 1024);
        if (revoked) return;
        // Bytes come back from Wails as base64-encoded string (Go []byte default).
        const blob =
          typeof bytes === 'string'
            ? new Blob([Uint8Array.from(atob(bytes), c => c.charCodeAt(0))], { type: mime })
            : new Blob([bytes as unknown as ArrayBuffer], { type: mime });
        createdUrl = URL.createObjectURL(blob);
        setPreviewUrl(createdUrl);
      } catch {
        /* preview failed; fall through to the filename chip */
      }
    })();
    return () => {
      revoked = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [fileId, mime]);

  if (previewUrl) {
    return (
      <figure className="inline-block max-w-xs my-2 rounded border border-neutral-300">
        <img src={previewUrl} alt={name} className="rounded-t max-h-64" />
        <figcaption className="text-xs px-2 py-1 text-neutral-600 flex justify-between items-center">
          <span className="truncate">{name}</span>
          <span>{humanSize(sizeBytes)}</span>
        </figcaption>
      </figure>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-2 rounded-full bg-neutral-100 border border-neutral-200 px-3 py-1 text-sm"
      title={`${name} (${mime})`}
    >
      <span aria-hidden>📎</span>
      <span className="truncate max-w-[16ch]">{name}</span>
      <span className="text-neutral-500 text-xs">{humanSize(sizeBytes)}</span>
      {staged && onRemove ? (
        <button
          type="button"
          aria-label={`remove ${name}`}
          onClick={() => onRemove(fileId)}
          className="text-neutral-500 hover:text-red-600"
        >
          ×
        </button>
      ) : null}
      {!staged && onDownload ? (
        <button
          type="button"
          aria-label={`download ${name}`}
          onClick={() => onDownload(fileId)}
          className="text-blue-600 hover:underline"
        >
          ↓
        </button>
      ) : null}
    </span>
  );
}
