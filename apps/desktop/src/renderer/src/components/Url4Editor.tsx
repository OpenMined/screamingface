import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Url4Field } from '@/components/Url4Field';

interface Url4EditorProps {
  initial: string;
  serverUrl: string;
  onRun: (expression: string) => void;
}

export function Url4Editor({ initial, serverUrl, onRun }: Url4EditorProps) {
  const [text, setText] = useState(initial);
  const isBlank = text.trim() === '';

  // Re-seed when the parent supplies a different source expression (e.g. a
  // different run); local edits to the same expression are preserved.
  useEffect(() => {
    setText(initial);
  }, [initial]);

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-md border border-border">
        <Url4Field value={text} onChange={setText} serverUrl={serverUrl} />
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
