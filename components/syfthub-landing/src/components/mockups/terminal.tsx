interface TerminalProps {
  lines: { prompt?: boolean; text: string; dimmed?: boolean }[];
  title?: string;
}

export function Terminal({ lines, title = "Terminal" }: TerminalProps) {
  return (
    <div className="w-full overflow-hidden rounded-xl border border-gray-200 bg-gray-950 shadow-2xl dark:border-gray-800">
      {/* Title bar */}
      <div className="flex items-center gap-2 border-b border-gray-800 px-4 py-3">
        <div className="flex gap-1.5">
          <div className="h-3 w-3 rounded-full bg-red-500/80" />
          <div className="h-3 w-3 rounded-full bg-yellow-500/80" />
          <div className="h-3 w-3 rounded-full bg-green-500/80" />
        </div>
        <span className="ml-2 text-xs text-gray-500 font-mono">{title}</span>
      </div>
      {/* Content */}
      <div className="p-5 font-mono text-sm leading-7">
        {lines.map((line, i) => (
          <div key={i} className={line.dimmed ? "text-gray-600" : "text-gray-300"}>
            {line.prompt && <span className="text-green-400 mr-2">$</span>}
            <span dangerouslySetInnerHTML={{ __html: line.text }} />
          </div>
        ))}
        <span className="inline-block h-4 w-2 bg-green-400 animate-cursor-blink" />
      </div>
    </div>
  );
}
