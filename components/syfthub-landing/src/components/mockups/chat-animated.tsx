"use client";

import { useState, useEffect, useRef } from "react";
import { useInView } from "@/components/animations/use-in-view";

export interface ChatMessage {
  avatar: string;
  avatarColor: string;
  name: string;
  time: string;
  content: React.ReactNode;
  delay: number;
  isBot?: boolean;
  botBadge?: string;
  bgClass?: string;
}

interface ChatAnimatedProps {
  messages: ChatMessage[];
  typingIndicatorDelay?: number;
  className?: string;
}

export function ChatAnimated({
  messages,
  typingIndicatorDelay = 600,
  className,
}: ChatAnimatedProps) {
  const [ref, isInView] = useInView();
  const [visibleCount, setVisibleCount] = useState(0);
  const [showTyping, setShowTyping] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!isInView) return;
    if (visibleCount >= messages.length) return;

    const nextMessage = messages[visibleCount];
    const prevDelay = visibleCount > 0 ? messages[visibleCount - 1].delay : 0;
    const waitTime = nextMessage.delay - prevDelay;

    if (nextMessage.isBot) {
      timeoutRef.current = setTimeout(() => {
        setShowTyping(true);
        timeoutRef.current = setTimeout(() => {
          setShowTyping(false);
          setVisibleCount((c) => c + 1);
        }, typingIndicatorDelay);
      }, waitTime);
    } else {
      timeoutRef.current = setTimeout(() => {
        setVisibleCount((c) => c + 1);
      }, waitTime);
    }

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [isInView, visibleCount, messages, typingIndicatorDelay]);

  return (
    <div ref={ref} className={className}>
      <div className="divide-y divide-gray-100">
        {/* ALL messages pre-rendered to reserve space */}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 px-5 py-4 transition-opacity duration-300 ${msg.bgClass ?? ""}`}
            style={{
              opacity: i < visibleCount ? 1 : 0,
              transform: i < visibleCount ? "translateY(0)" : "translateY(8px)",
              transition: "opacity 0.3s ease-out, transform 0.3s ease-out",
            }}
          >
            <div
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${msg.avatarColor}`}
            >
              {msg.avatar}
            </div>
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-[13px] font-bold text-gray-900">
                  {msg.name}
                </span>
                {msg.isBot && msg.botBadge && (
                  <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-600">
                    {msg.botBadge}
                  </span>
                )}
                <span className="text-[11px] text-gray-400">{msg.time}</span>
              </div>
              <div className="mt-0.5 text-[13px] leading-relaxed text-gray-600">
                {msg.content}
              </div>
            </div>
          </div>
        ))}
        {/* Typing indicator — fixed height wrapper always in DOM */}
        <div
          className="flex gap-3 px-5 py-4"
          style={{
            opacity: showTyping ? 1 : 0,
            height: showTyping ? "auto" : 0,
            overflow: "hidden",
            padding: showTyping ? undefined : "0 20px",
            transition: "opacity 0.2s ease-out",
          }}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-xs font-bold text-white">
            AI
          </div>
          <div className="flex items-center gap-1 pt-2">
            <span className="h-2 w-2 rounded-full bg-gray-300 animate-pulse-soft" />
            <span
              className="h-2 w-2 rounded-full bg-gray-300 animate-pulse-soft"
              style={{ animationDelay: "200ms" }}
            />
            <span
              className="h-2 w-2 rounded-full bg-gray-300 animate-pulse-soft"
              style={{ animationDelay: "400ms" }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
