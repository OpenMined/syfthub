/**
 * Type declarations for lucide-react individual ESM icon path imports.
 * e.g. `import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down'`
 *
 * The installed version of lucide-react ships JS files for each icon but no
 * per-icon .d.ts files. This wildcard declaration makes TypeScript resolve
 * those imports to the correct LucideIcon type.
 */
declare module 'lucide-react/dist/esm/icons/*' {
  import type { LucideIcon } from 'lucide-react';
  const icon: LucideIcon;
  export default icon;
}
