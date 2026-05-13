/**
 * Markdown rewriter for the `attachment://{file_id}` URI scheme.
 *
 * Agents reference attachments inline:
 *     Here's the chart you asked for: ![chart](attachment://att-abc123)
 *
 * Rewrites those URIs to sentinel <span> tags that ChatMessage swaps for an
 * <AttachmentChip> at render time, avoiding a full remark plugin dependency.
 *
 * See docs/architecture/attachments.md.
 */

export const ATTACHMENT_URI_PREFIX = 'attachment://';

/**
 * Replaces every occurrence of `attachment://{file_id}` (in markdown source)
 * with a sentinel HTML span that ChatMessage swaps for an <AttachmentChip>
 * during rendering.
 */
export function rewriteAttachmentLinks(markdown: string): string {
  // Match the URI inside both markdown image syntax and bare links.
  const imgPattern = /!\[([^\]]*)\]\(attachment:\/\/([\w-]+)\)/g;
  const linkPattern = /\[([^\]]*)\]\(attachment:\/\/([\w-]+)\)/g;
  const barePattern = /(^|\s)attachment:\/\/([\w-]+)/g;

  return markdown
    .replace(imgPattern, (_m, alt, fid) => sentinel(fid, alt || fid))
    .replace(linkPattern, (_m, text, fid) => sentinel(fid, text || fid))
    .replace(barePattern, (_m, lead, fid) => `${lead}${sentinel(fid, fid)}`);
}

function sentinel(fileId: string, label: string): string {
  // Encode label so it can survive HTML attribute embedding.
  const safeLabel = label.replace(/"/g, '&quot;').replace(/</g, '&lt;');
  return `<span data-attachment-file-id="${fileId}" data-attachment-label="${safeLabel}"></span>`;
}

/**
 * extractAttachmentRefs scans rendered markdown HTML for attachment sentinels
 * and returns the file_ids referenced. The chat renderer uses this to
 * pre-fetch metadata for all attachments referenced in a single message.
 */
export function extractAttachmentRefs(html: string): string[] {
  const out: string[] = [];
  const re = /data-attachment-file-id="([\w-]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    out.push(m[1]);
  }
  return out;
}
