interface ChatMessageProps {
  avatar: string;
  name: string;
  message: string;
  isBot?: boolean;
  time?: string;
}

export function ChatMessage({ avatar, name, message, isBot, time }: ChatMessageProps) {
  return (
    <div className="flex gap-3">
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold ${
        isBot ? "bg-indigo-100 text-indigo-600" : "bg-gray-100 text-gray-600"
      }`}>
        {avatar}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-gray-900">{name}</span>
          {time && <span className="text-xs text-gray-400">{time}</span>}
        </div>
        <p className="mt-0.5 text-sm leading-relaxed text-gray-600">{message}</p>
      </div>
    </div>
  );
}

interface ChatContainerProps {
  children: React.ReactNode;
  className?: string;
}

export function ChatContainer({ children, className = "" }: ChatContainerProps) {
  return (
    <div className={`space-y-5 rounded-xl border border-gray-200 bg-white p-5 shadow-lg ${className}`}>
      {children}
    </div>
  );
}
