"use client";

import { cn } from "@/lib/utils";
import { useInView } from "./use-in-view";

interface AnimatedSectionProps {
  children: React.ReactNode;
  animation?: string;
  delay?: number;
  className?: string;
  as?: React.ElementType;
  threshold?: number;
  rootMargin?: string;
}

export function AnimatedSection({
  children,
  animation = "animate-fade-in-up",
  delay,
  className,
  as: Component = "div",
  threshold,
  rootMargin,
}: AnimatedSectionProps) {
  const [ref, isInView] = useInView({ threshold, rootMargin });

  return (
    <Component
      ref={ref}
      className={cn(isInView ? animation : "opacity-0", className)}
      style={delay ? { animationDelay: `${delay}ms` } : undefined}
    >
      {children}
    </Component>
  );
}
