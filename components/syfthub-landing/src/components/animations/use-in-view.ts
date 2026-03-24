"use client";

import { useState, useRef, useCallback, useEffect } from "react";

interface UseInViewOptions {
  threshold?: number;
  rootMargin?: string;
  once?: boolean;
}

export function useInView(
  options?: UseInViewOptions
): [React.RefCallback<HTMLElement>, boolean] {
  const { threshold = 0.15, rootMargin = "0px 0px -60px 0px", once = true } =
    options ?? {};
  const [isInView, setIsInView] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const elementRef = useRef<HTMLElement | null>(null);

  // Clean up observer
  useEffect(() => {
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  const refCallback = useCallback(
    (node: HTMLElement | null) => {
      // Disconnect previous observer
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }

      if (!node) {
        elementRef.current = null;
        return;
      }

      elementRef.current = node;

      // Feature detection
      if (typeof IntersectionObserver === "undefined") {
        setIsInView(true);
        return;
      }

      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            setIsInView(true);
            if (once) {
              observer.disconnect();
              observerRef.current = null;
            }
          } else if (!once) {
            setIsInView(false);
          }
        },
        { threshold, rootMargin }
      );

      observer.observe(node);
      observerRef.current = observer;
    },
    [threshold, rootMargin, once]
  );

  return [refCallback, isInView];
}
