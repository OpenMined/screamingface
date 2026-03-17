import { useEffect, useRef, useState, useCallback } from 'react';
import { Trash2, Copy, Check, ChevronRight, ChevronDown, Maximize2, Minimize2 } from 'lucide-react';

interface ServerLogsProps {
  logs: string[];
  onClear: () => void;
}

type LogLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical' | 'system';

const LEVEL_REGEX = /^(DEBUG|INFO|WARNING|ERROR|CRITICAL):\s*/;

function parseLevel(line: string): LogLevel {
  const match = line.match(LEVEL_REGEX);
  if (match) return match[1].toLowerCase() as LogLevel;
  return 'system';
}

const LEVEL_STYLES: Record<LogLevel, string> = {
  debug: 'text-[#6b6580]',
  info: 'text-[#8a8699]',
  warning: 'text-[#f8c073]',
  error: 'text-[#cc677b]',
  critical: 'text-[#cc677b] font-bold',
  system: 'text-[#53bea9]',
};

const LEVEL_BADGE: Record<LogLevel, { text: string; className: string } | null> = {
  debug: { text: 'DBG', className: 'bg-[#2a2633] text-[#6b6580]' },
  info: { text: 'INF', className: 'bg-[#1a2530] text-[#52a8c5]' },
  warning: { text: 'WRN', className: 'bg-[#2a2215] text-[#f8c073]' },
  error: { text: 'ERR', className: 'bg-[#2a1a20] text-[#cc677b]' },
  critical: { text: 'CRT', className: 'bg-[#2a1a20] text-[#cc677b] font-bold' },
  system: null,
};

const FOLD_THRESHOLD = 80;

function LogLine({ line }: { line: string }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const level = parseLevel(line);
  const badge = LEVEL_BADGE[level];
  const isFoldable = line.length > FOLD_THRESHOLD;

  // Strip the level prefix for cleaner display (badge already shows it)
  const match = line.match(LEVEL_REGEX);
  const content = match ? line.slice(match[0].length) : line;

  const displayText = isFoldable && !expanded ? content.slice(0, FOLD_THRESHOLD) + '…' : content;

  const handleCopyLine = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(line);
    setCopied(true);
    setTimeout(() => setCopied(false), 1000);
  };

  return (
    <div className={`group relative flex items-start gap-1.5 py-[1px] ${LEVEL_STYLES[level]}`}>
      {badge ? (
        <span
          className={`mt-[1px] inline-flex shrink-0 items-center rounded px-1 text-[9px] font-medium leading-[14px] ${badge.className}`}
        >
          {badge.text}
        </span>
      ) : (
        <span className="inline-flex w-[28px] shrink-0" />
      )}
      <div className="flex min-w-0 flex-1 items-start">
        {isFoldable ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex min-w-0 cursor-pointer items-start gap-0.5 text-left"
          >
            {expanded ? (
              <ChevronDown className="mt-[2px] h-3 w-3 shrink-0 opacity-50" />
            ) : (
              <ChevronRight className="mt-[2px] h-3 w-3 shrink-0 opacity-50" />
            )}
            <span className={expanded ? 'whitespace-pre-wrap break-all' : 'truncate'}>
              {displayText}
            </span>
          </button>
        ) : (
          <span className="whitespace-pre-wrap break-all">{displayText}</span>
        )}
      </div>
      <button
        onClick={handleCopyLine}
        className="mt-[1px] shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
        title="Copy line"
      >
        {copied ? (
          <Check className="h-3 w-3 text-chart-3" />
        ) : (
          <Copy className="h-3 w-3 text-muted-foreground hover:text-foreground" />
        )}
      </button>
    </div>
  );
}

export function ServerLogs({ logs, onClear }: ServerLogsProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);

  // Track whether user has scrolled up
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    setAutoScroll(atBottom);
  }, []);

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs.length, autoScroll]);

  // Escape key exits fullscreen
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fullscreen]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(logs.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const wrapperClass = fullscreen
    ? 'fixed inset-0 z-50 flex flex-col bg-card'
    : 'rounded-lg border border-border bg-card';

  const scrollClass = fullscreen
    ? 'flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed'
    : 'h-48 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed';

  return (
    <div className={wrapperClass}>
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <h3 className="text-xs font-medium text-muted-foreground">
          Logs{fullscreen && <span className="ml-2 text-[10px] opacity-50">ESC to exit</span>}
        </h3>
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
          <button
            onClick={() => setFullscreen((v) => !v)}
            className="text-muted-foreground transition-colors hover:text-foreground"
            title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {fullscreen ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
      <div ref={containerRef} onScroll={handleScroll} className={scrollClass}>
        {logs.length === 0 ? (
          <span className="italic text-muted-foreground">No logs yet</span>
        ) : (
          logs.map((line, i) => <LogLine key={i} line={line} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
