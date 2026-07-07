import React from 'react';

/**
 * Mock for framer-motion used in component tests.
 * Replaces AnimatePresence and motion.* with pass-through elements
 * that render without animations.
 */

const MOTION_PROPS = new Set([
  'initial',
  'animate',
  'exit',
  'transition',
  'variants',
  'whileHover',
  'whileTap',
  'whileFocus',
  'whileInView',
  'layout',
  'layoutId',
  'onAnimationComplete',
  'onAnimationStart',
  'dragConstraints',
  'drag',
  'dragElastic',
  'dragMomentum',
  'dragPropagation',
  'dragTransition',
  'onDrag',
  'onDragEnd',
  'onDragStart',
  'whileDrag'
]);

function filterMotionProps(props: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(props).filter(([key]) => !MOTION_PROPS.has(key)));
}

// AnimatePresence renders children directly (no animation wrapper)
export function AnimatePresence({ children }: Readonly<{ children?: React.ReactNode }>) {
  return <>{children}</>;
}

// motion.div, motion.span, etc. render the native element with motion props filtered out
export const motion = new Proxy(
  {} as Record<string, React.ForwardRefExoticComponent<Record<string, unknown>>>,
  {
    get(_target, property) {
      if (typeof property === 'symbol' || property === '__esModule') return;

      const Component = React.forwardRef<unknown, Record<string, unknown>>(function MotionComponent(
        { children, ...props },
        ref
      ) {
        return React.createElement(
          property,
          { ...filterMotionProps(props), ref },
          children as React.ReactNode
        );
      });
      Component.displayName = `motion.${property}`;
      return Component;
    }
  }
);
