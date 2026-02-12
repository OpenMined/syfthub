/**
 * TypeScript declarations for lucide-react direct ESM imports.
 *
 * Direct imports from lucide-react/dist/esm/icons/* reduce bundle size
 * by avoiding barrel file overhead during development and ensuring
 * optimal tree-shaking in production builds.
 *
 * @see https://lucide.dev/guide/packages/lucide-react
 */

declare module 'lucide-react/dist/esm/icons/*' {
  import type { LucideIcon } from 'lucide-react';
  const icon: LucideIcon;
  export default icon;
}
