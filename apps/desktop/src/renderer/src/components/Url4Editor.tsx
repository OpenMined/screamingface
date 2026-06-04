import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Url4Viewer } from '@/components/Url4Viewer';

interface Url4EditorProps {
  initial: string;
  serverUrl: string;
  onRun: (expression: string) => void;
}

export function Url4Editor({ initial, serverUrl, onRun }: Url4EditorProps) {
  const [text, setText] = useState(initial);
  const isBlank = text.trim() === '';

  // Re-seed the editor when the parent supplies a different source
  // expression (e.g. a different leaderboard entry). Local edits to the
  // same expression are preserved because the effect only fires when
  // `initial` actually changes.
  useEffect(() => {
    setText(initial);
  }, [initial]);

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
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setText(initial)}
          disabled={text === initial}
          className="self-start"
        >
          Reset
        </Button>
        <Button
          type="button"
          variant="default"
          size="sm"
          onClick={() => onRun(text)}
          disabled={isBlank}
          className="self-start"
        >
          Re-run
        </Button>
      </div>
    </div>
  );
}
