# Landing Page Animations Plan

## Architecture Decisions
- Pages remain Server Components; animation wrappers are Client Components with "use client"
- No animation library (framer-motion etc.) -- pure CSS keyframes + IntersectionObserver hook
- Custom `useInView` hook (ref callback pattern) is foundation for all scroll-triggered animations
- 6 shared animation components in `src/components/animations/`
- 2 animated mockup components in `src/components/mockups/`
- Page-specific animated sections in co-located files (e.g., `src/app/h4-pkm/search-demo-animated.tsx`)

## Patterns Discovered
- `tw-animate-css` is installed and imported in globals.css alongside shadcn styles
- Tailwind v4 uses `@theme inline` syntax -- custom animation vars go in inline styles, not theme config
- Existing Terminal, BrowserFrame, ChatMessage, DashboardMock are Server Components (no "use client")
- globals.css already has fade-in-up, cursor-blink, pulse-soft keyframes with utility classes
- SectionBreak component is defined inline in h8-publishers/page.tsx, not shared

## Blast Radius Notes
- globals.css: consumed by ALL files -- any keyframe name collision would affect everything
- useInView hook: imported by all 5 animation components + 2 animated mockups
- AnimatedSection: imported by all 7 page files
- Each page file is standalone -- no cross-page imports

## Constraints
- Only opacity + transform for animations (GPU-composited, no layout thrash)
- prefers-reduced-motion must disable all animations via 0.01ms duration trick
- Existing mockup components must NOT be modified
- Pages must NOT get "use client" directive
