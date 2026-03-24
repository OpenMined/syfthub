"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { useInView } from "./use-in-view";

interface StaggeredListProps {
  children: React.ReactNode;
  staggerMs?: number;
  animation?: string;
  className?: string;
  as?: React.ElementType;
}

export function StaggeredList({
  children,
  staggerMs = 100,
  animation = "animate-fade-in-up",
  className,
  as: Component = "div",
}: StaggeredListProps) {
  const [ref, isInView] = useInView();

  return (
    <Component ref={ref} className={className}>
      {React.Children.map(children, (child, index) => (
        <div
          className={cn(isInView ? animation : "opacity-0")}
          style={
            isInView
              ? { animationDelay: `${index * staggerMs}ms` }
              : undefined
          }
        >
          {child}
        </div>
      ))}
    </Component>
  );
}
