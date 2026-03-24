interface BrowserFrameProps {
  url?: string;
  children: React.ReactNode;
  className?: string;
}

export function BrowserFrame({ url = "app.syfthub.com", children, className = "" }: BrowserFrameProps) {
  return (
    <div className={`overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl ${className}`}>
      {/* Address bar */}
      <div className="flex items-center gap-3 border-b border-gray-100 bg-gray-50 px-4 py-2.5">
        <div className="flex gap-1.5">
          <div className="h-2.5 w-2.5 rounded-full bg-gray-300" />
          <div className="h-2.5 w-2.5 rounded-full bg-gray-300" />
          <div className="h-2.5 w-2.5 rounded-full bg-gray-300" />
        </div>
        <div className="flex-1 rounded-md bg-gray-100 px-3 py-1">
          <span className="text-xs text-gray-400">{url}</span>
        </div>
      </div>
      {/* Content */}
      <div>
        {children}
      </div>
    </div>
  );
}
