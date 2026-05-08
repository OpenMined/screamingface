import { useEffect, useRef, useState } from 'react';

interface Token {
  type: 'paren' | 'comma' | 'ws' | 'url' | 'text' | 'intent_sep' | 'intent';
  value: string;
  depth: number;
}

interface Url4ViewerProps {
  expression: string;
  serverUrl: string;
  fetchFn?: (url: string) => Promise<{ ok: boolean; json: () => unknown }>;
  mode?: 'inline' | 'expanded';
  className?: string;
}

const TOKEN_CLASSES: Record<Token['type'], string> = {
  url: 'text-chart-3',
  text: 'text-chart-1',
  paren: 'text-muted-foreground',
  comma: 'text-muted-foreground',
  intent: 'text-chart-5',
  intent_sep: 'text-chart-5',
  ws: '',
};

export function Url4Viewer({
  expression,
  serverUrl,
  fetchFn,
  mode = 'inline',
  className = '',
}: Url4ViewerProps) {
  const [tokens, setTokens] = useState<Token[] | null>(null);
  const [error, setError] = useState(false);
  const cacheRef = useRef<Map<string, Token[]>>(new Map());
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!expression) {
      setTokens(null);
      return;
    }

    // Return cached result immediately
    const cached = cacheRef.current.get(expression);
    if (cached) {
      setTokens(cached);
      setError(false);
      return;
    }

    // Debounce the fetch
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        const url = `${serverUrl}/ensemble/highlight?q=${encodeURIComponent(expression)}`;
        const res = fetchFn ? await fetchFn(url) : await fetch(url);
        if (!res.ok) {
          console.error(`[Url4Viewer] highlight request failed: ${res.status} ${res.statusText}`);
          setError(true);
          return;
        }
        const data = res.json() as { tokens: Token[] };
        cacheRef.current.set(expression, data.tokens);
        setTokens(data.tokens);
        setError(false);
      } catch (err) {
        console.error('[Url4Viewer] highlight request error:', err);
        setError(true);
      }
    }, 300);

    return () => clearTimeout(timerRef.current);
  }, [expression, serverUrl, fetchFn]);

  // Fallback: plain monospace text
  if (!tokens || error) {
    return (
      <code className={`block font-mono text-xs text-muted-foreground ${className}`}>
        {expression}
      </code>
    );
  }

  if (mode === 'expanded') {
    return (
      <code className={`block font-mono text-xs whitespace-pre ${className}`}>
        {renderExpanded(tokens)}
      </code>
    );
  }

  return (
    <code className={`block font-mono text-xs ${className}`}>
      {tokens.map((t, i) => (
        <span key={i} className={TOKEN_CLASSES[t.type]}>
          {t.value}
        </span>
      ))}
    </code>
  );
}

function renderExpanded(tokens: Token[]): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const indent = (depth: number) => '  '.repeat(depth);

  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    const cls = TOKEN_CLASSES[t.type];

    if (t.type === 'paren' && t.value === '(') {
      nodes.push(
        <span key={i} className={cls}>
          {t.value}
        </span>,
      );
      // Newline + indent after opening paren
      const nextDepth = t.depth + 1;
      nodes.push(<span key={`${i}-nl`}>{'\n' + indent(nextDepth)}</span>);
    } else if (t.type === 'paren' && t.value === ')') {
      // Newline + indent before closing paren
      nodes.push(<span key={`${i}-nl`}>{'\n' + indent(t.depth)}</span>);
      nodes.push(
        <span key={i} className={cls}>
          {t.value}
        </span>,
      );
    } else if (t.type === 'comma') {
      nodes.push(
        <span key={i} className={cls}>
          {t.value}
        </span>,
      );
      // Newline + indent after comma (skip the ws token that follows)
      nodes.push(<span key={`${i}-nl`}>{'\n' + indent(t.depth)}</span>);
      // Skip the whitespace token after comma
      if (i + 1 < tokens.length && tokens[i + 1].type === 'ws') {
        i++;
      }
    } else if (t.type === 'ws') {
      // In expanded mode, whitespace is handled by indentation
      nodes.push(
        <span key={i} className={cls}>
          {t.value}
        </span>,
      );
    } else {
      nodes.push(
        <span key={i} className={cls}>
          {t.value}
        </span>,
      );
    }
  }
  return nodes;
}
