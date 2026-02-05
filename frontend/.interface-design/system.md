# SyftHub Design System

Extracted from existing codebase. Use these patterns for consistency.

---

## Direction

**Visual approach:** Clean, professional, border-first depth
**Feel:** Minimal, technical, trustworthy
**Framework:** React 19 + Tailwind CSS v4 + shadcn/ui + Radix primitives

---

## Typography

### Fonts
- **Headings:** Rubik (font-rubik)
- **Body:** Inter (font-inter)

### Scale
| Element | Class | Size |
|---------|-------|------|
| Page title | `text-3xl font-semibold font-rubik` | 30px |
| Section title | `text-xl font-medium font-rubik` | 20px |
| Card title | `text-lg font-medium font-rubik` | 18px |
| Subsection | `text-sm font-medium font-rubik` | 14px |
| Body | `text-sm font-inter` | 14px |
| Body large | `text-base font-inter` | 16px |
| Caption | `text-xs font-inter` | 12px |
| Tiny (labels) | `text-[10px] font-inter` | 10px |

### Text colors
- Primary: `text-foreground`
- Secondary: `text-muted-foreground`
- Links: `text-primary hover:underline`

---

## Spacing

### Base unit: 4px (0.25rem)

### Scale
| Token | Value | Tailwind |
|-------|-------|----------|
| xs | 4px | `gap-1`, `p-1` |
| sm | 8px | `gap-2`, `p-2` |
| md | 12px | `gap-3`, `p-3` |
| lg | 16px | `gap-4`, `p-4` |
| xl | 24px | `gap-6`, `p-6` |
| 2xl | 32px | `gap-8`, `p-8` |

### Common patterns
- Card padding: `p-5` or `p-6`
- Card internal gap: `gap-6` or `space-y-6`
- Section gap: `space-y-8`
- Page padding: `px-6 py-8`
- Between form fields: `space-y-4`
- Between inline elements: `gap-2` or `gap-3`

---

## Radius

### Scale
| Token | Value | Tailwind | Usage |
|-------|-------|----------|-------|
| sm | 4px | `rounded-sm` | Small elements |
| md | 6px | `rounded-md` | Buttons, inputs |
| lg | 8px | `rounded-lg` | Secondary cards, inputs |
| xl | 12px | `rounded-xl` | Cards, modals, primary containers |
| 2xl | 16px | `rounded-2xl` | Message bubbles, hero elements |
| full | 50% | `rounded-full` | Avatars, status dots, pills |

### Default by component
- Cards: `rounded-xl`
- Modals: `rounded-xl`
- Buttons: `rounded-md`
- Inputs: `rounded-lg`
- Badges: `rounded-md`
- Message bubbles: `rounded-2xl`

---

## Depth

### Strategy: Border-first
Prefer borders over shadows for elevation. Shadows reserved for:
- Interactive hover states
- Modals and overlays

### Elevation levels
| Level | Usage | Classes |
|-------|-------|---------|
| 0 | Flat content | `border border-border` |
| 1 | Cards at rest | `border border-border shadow-sm` |
| 2 | Hover states | `border border-border shadow-md` |
| 3 | Modals, dropdowns | `border border-border shadow-xl` |

### Modal backdrop
```css
bg-black/50 backdrop-blur-sm
```

---

## Colors

### Semantic tokens (use these, not raw colors)

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--background` | #ffffff | #0f0e13 | Page background |
| `--foreground` | #272532 | #f4f4f6 | Primary text |
| `--card` | #ffffff | #151419 | Card background |
| `--muted` | #f7f6f9 | #1a1820 | Muted backgrounds |
| `--muted-foreground` | #5e5a72 | #9e99ad | Secondary text |
| `--accent` | #f1f0f4 | #252330 | Hover states |
| `--primary` | #272532 | #f4f4f6 | Primary actions |
| `--secondary` | #6976ae | #8892c4 | Secondary actions |
| `--border` | #ecebef | #3a3748 | Borders |
| `--destructive` | #ef4444 | #f87171 | Danger actions |

### Chart/accent colors
| Token | Light | Usage |
|-------|-------|-------|
| `--chart-1` | #64bb62 | Success, green accents |
| `--chart-2` | #6976ae | Info, blue accents |
| `--chart-3` | #937098 | Purple accents |

### Status colors (inline, not tokens)
- Active: `bg-green-500`
- Warning: `bg-yellow-500`
- Inactive/Error: `bg-red-500`

---

## Components

### Button

**Sizes:**
| Size | Height | Padding | Class |
|------|--------|---------|-------|
| sm | 32px | 12px | `h-8 px-3` |
| default | 36px | 16px/8px | `h-9 px-4 py-2` |
| lg | 40px | 24px | `h-10 px-6` |
| icon | 36px | - | `size-9` |

**Variants:**
- `default`: `bg-primary text-primary-foreground`
- `secondary`: `bg-secondary text-secondary-foreground`
- `outline`: `border bg-background`
- `ghost`: `hover:bg-accent`
- `destructive`: `bg-destructive text-white`

### Input

**Sizes:**
| Size | Height | Padding |
|------|--------|---------|
| sm | 32px | 8px |
| default | 40px | 12px |
| lg | 48px | 16px |

**Base classes:**
```
rounded-lg border border-input bg-background px-3 py-2
focus:border-primary focus:ring-2 focus:ring-primary/10
```

### Card

**Structure:**
```tsx
<Card>           // rounded-xl border py-6 gap-6
  <CardHeader>   // px-6 gap-1.5
    <CardTitle>  // font-semibold leading-none
    <CardDescription> // text-muted-foreground text-sm
  </CardHeader>
  <CardContent>  // px-6
  <CardFooter>   // px-6
</Card>
```

### Modal

**Sizes:**
| Size | Max-width |
|------|-----------|
| sm | 384px |
| md | 448px |
| lg | 512px |
| xl | 576px |

**Structure:**
```tsx
// Backdrop
bg-black/50 backdrop-blur-sm

// Modal
border-border bg-card rounded-xl border shadow-xl

// Header padding
px-6 pt-6 pb-2

// Content padding
px-6 pb-6
```

### Badge

**Base:** `rounded-md border px-2.5 py-0.5 text-xs font-semibold`

**Variants:**
- `default`: `bg-primary text-primary-foreground`
- `secondary`: `bg-secondary text-secondary-foreground`
- `outline`: `text-foreground`
- `destructive`: `bg-destructive text-destructive-foreground`

### Tabs

**List:** `bg-muted rounded-md p-1 h-10`
**Trigger:** `rounded-sm px-3 py-1.5 text-sm font-medium`
**Active state:** `bg-background text-foreground shadow-sm`

---

## Layout

### Page structure
```tsx
<div className="bg-background min-h-screen pb-24">
  <PageHeader title="..." />
  <div className="mx-auto max-w-6xl px-6 py-8">
    {/* content */}
  </div>
</div>
```

### Sidebar
- Width: `w-20` (80px)
- Position: `fixed left-0 top-0 h-screen`
- Background: `bg-background border-r border-border`

### Content offset
When sidebar is present: `pl-24` (96px, sidebar + gap)

### Max widths
| Usage | Class |
|-------|-------|
| Narrow content (chat) | `max-w-3xl` or `max-w-4xl` |
| Standard pages | `max-w-6xl` |
| Full bleed | no max-width |

### Grid
- Browse cards: `grid gap-4 md:grid-cols-2 lg:grid-cols-3`
- Settings sidebar: `w-48` fixed

---

## Interaction

### Transitions
**Default:** `transition-colors` (150ms)
**With shadow:** `transition-colors transition-shadow`
**Duration:** Use defaults (no custom durations)

### Focus states
```
focus-visible:outline-none
focus-visible:ring-2
focus-visible:ring-ring/50
focus-visible:border-ring
```

### Hover patterns
- Buttons: opacity change (`hover:bg-primary/90`)
- Cards: shadow (`hover:shadow-md`)
- Links: underline or color shift
- Icons: color from muted to foreground

### Disabled states
```
disabled:pointer-events-none
disabled:opacity-50
disabled:cursor-not-allowed
```

---

## Animation

### Modal enter/exit
```tsx
initial={{ opacity: 0, scale: 0.95, y: 20 }}
animate={{ opacity: 1, scale: 1, y: 0 }}
exit={{ opacity: 0, scale: 0.95, y: 20 }}
transition={{ type: 'spring', duration: 0.3 }}
```

### Respect reduced motion
```css
@media (prefers-reduced-motion: reduce) {
  animation-duration: 0.01ms !important;
  transition-duration: 0.01ms !important;
}
```

---

## Icons

**Library:** Lucide React
**Import pattern:**
```tsx
import IconName from 'lucide-react/dist/esm/icons/icon-name';
```

**Sizes:**
| Context | Class |
|---------|-------|
| Inline with text | `h-4 w-4` |
| Button icon | `h-4 w-4` or `h-5 w-5` |
| Standalone | `h-5 w-5` |
| Large/hero | `h-7 w-7` or `h-8 w-8` |

**Accessibility:**
```tsx
<Icon className="h-4 w-4" aria-hidden="true" />
// Or with label:
<Icon className="h-4 w-4" aria-label="Description" />
```

---

## Accessibility

### Required patterns
- All interactive elements focusable
- Focus trap in modals
- Escape to close modals
- `aria-label` on icon-only buttons
- `aria-hidden="true"` on decorative icons
- `role="dialog"` and `aria-modal="true"` on modals
- Touch targets minimum 44×44px (or 32px with spacing)

### Touch optimization
```css
touch-action: manipulation;
-webkit-tap-highlight-color: transparent;
```
