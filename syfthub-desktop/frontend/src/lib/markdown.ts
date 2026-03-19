/** Splits a markdown string into its YAML frontmatter block and body. */
export function parseFrontmatter(content: string): { frontmatter: string; body: string } {
  const trimmed = content.trimStart();

  if (!trimmed.startsWith('---')) {
    return { frontmatter: '', body: content };
  }

  const endIndex = trimmed.indexOf('---', 3);
  if (endIndex === -1) {
    return { frontmatter: '', body: content };
  }

  const frontmatterEnd = endIndex + 3;
  const frontmatter = trimmed.slice(0, frontmatterEnd);
  const body = trimmed.slice(frontmatterEnd).replace(/^\n+/, '');

  return { frontmatter, body };
}
