import { useState } from 'react';
import { Url4Viewer } from '@/components/Url4Viewer';

interface Url4EditorProps {
  initial: string;
  serverUrl: string;
  onRun: (expression: string) => void;
}

export function Url4Editor({ initial, serverUrl, onRun }: Url4EditorProps) {
  const [text, setText] = useState(initial);
  const isBlank = text.trim() === '';

  return (
    <div className="flex flex-col gap-3">
      <textarea
        aria-label="URL4 expression editor"
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        className="min-h-[120px] rounded-md border border-border bg-background p-3 font-mono text-sm"
      />
      <div className="text-xs text-muted-foreground">Preview</div>
      <div className="rounded-md border border-border p-3">
        <Url4Viewer expression={text} serverUrl={serverUrl} mode="expanded" />
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setText(initial)}
          disabled={text === initial}
          className="self-start rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={() => onRun(text)}
          disabled={isBlank}
          className="self-start rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          Re-run
        </button>
      </div>
    </div>
  );
}
