"use client";

import { Button } from "@/components/ui/button";

interface NavbarProps {
  ctaText: string;
  accentColor?: string;
}

export function Navbar({ ctaText, accentColor = "bg-white text-gray-950" }: NavbarProps) {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-gray-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
            <span className="text-sm font-bold">S</span>
          </div>
          <span className="text-lg font-semibold tracking-tight">SyftHub</span>
        </div>
        <Button
          className={`rounded-full px-5 py-2 text-sm font-semibold ${accentColor} hover:opacity-90 transition-opacity`}
          size="sm"
        >
          {ctaText}
        </Button>
      </div>
    </nav>
  );
}
