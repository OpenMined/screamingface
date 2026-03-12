import { useEffect, useRef, useState } from 'react';
import { Trash2, Copy, Check } from 'lucide-react';

interface ServerLogsProps {
  logs: string[];
  onClear: () => void;
}

export function ServerLogs({ logs, onClear }: ServerLogsProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(logs.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <h3 className="text-xs font-medium text-muted-foreground">Logs</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            disabled={logs.length === 0}
            className="text-muted-foreground transition-colors hover:text-foreground disabled:opacity-30"
            title="Copy logs"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-chart-3" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            onClick={onClear}
            className="text-muted-foreground transition-colors hover:text-foreground"
            title="Clear logs"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <div className="h-48 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
        {logs.length === 0 ? (
          <span className="italic">No logs yet</span>
        ) : (
          logs.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
