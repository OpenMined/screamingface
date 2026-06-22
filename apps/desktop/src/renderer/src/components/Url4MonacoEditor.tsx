// apps/desktop/src/renderer/src/components/Url4MonacoEditor.tsx
//
// The url4 expression editor on Monaco (SF-249): syntax highlighting (Monarch),
// static autocomplete, and live validation squiggles from /ensemble/highlight.
// Read-only by default; pass onChange (and readOnly={false}) to edit. Default
// export so it can be React.lazy()'d (keeps the ~7MB Monaco chunk out of the
// main bundle). Use the lazy `Url4Field` wrapper rather than this directly.
import { useRef } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
// Side-effect: bundle Monaco (no CDN) before it mounts.
import '@/lib/monaco-setup';
import { registerUrl4Language, setUrl4SpecNames } from '@/lib/url4-language';
import { clampEditorHeight } from '@/lib/editor-height';

interface Props {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  serverUrl: string;
  className?: string;
  maxContentHeight?: number | null;
}

export default function Url4MonacoEditor({
  value,
  onChange,
  readOnly,
  serverUrl,
  className,
  maxContentHeight = 360,
}: Props) {
  const ro = readOnly ?? onChange === undefined;
  const wrapRef = useRef<HTMLDivElement>(null);

  const handleMount: OnMount = (editor, monaco) => {
    registerUrl4Language(monaco);
    const model = editor.getModel();
    if (model) monaco.editor.setModelLanguage(model, 'url4');

    // Auto-grow to fit content (capped) so it reads like a highlighted block.
    const applyHeight = (): void => {
      const h = clampEditorHeight(editor.getContentHeight(), maxContentHeight);
      if (wrapRef.current) wrapRef.current.style.height = `${h}px`;
      editor.layout();
    };
    editor.onDidContentSizeChange(applyHeight);
    applyHeight();

    // Spec names for autocomplete (best-effort, cached for the shared provider).
    void (async () => {
      try {
        const res = await window.electronAPI.server.fetch(
          `${serverUrl}/plugins/url4-specs/settings`,
        );
        if (res.ok) {
          const data = JSON.parse(res.body) as { specs?: Record<string, unknown> };
          if (data.specs) setUrl4SpecNames(Object.keys(data.specs));
        }
      } catch {
        /* offline — skip */
      }
    })();

    // NOTE: no server-side validation markers. /ensemble/highlight parses with
    // the base url4 grammar, which rejects the ensemble fan-out shape
    // `url*(...)` that /ensemble actually runs — so it false-errors on valid
    // specs. Highlighting is client-side (Monarch); the run is the source of
    // truth for errors. (Re-add markers if the server gains a validator that
    // matches the executor.)
  };

  return (
    <div ref={wrapRef} className={className} style={{ minHeight: 28 }}>
      <Editor
        language="url4"
        value={value}
        onChange={(v) => onChange?.(v ?? '')}
        theme="vs-dark"
        height="100%"
        options={{
          readOnly: ro,
          domReadOnly: ro,
          minimap: { enabled: false },
          lineNumbers: 'on',
          glyphMargin: false,
          folding: false,
          lineDecorationsWidth: 4,
          lineNumbersMinChars: 2,
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          fontSize: 12,
          padding: { top: 6, bottom: 6 },
          renderLineHighlight: 'none',
          overviewRulerLanes: 0,
          hideCursorInOverviewRuler: true,
          scrollbar: {
            horizontalScrollbarSize: 0,
            verticalScrollbarSize: 8,
            alwaysConsumeMouseWheel: false,
          },
          automaticLayout: true,
          contextmenu: !ro,
          fixedOverflowWidgets: true,
        }}
        onMount={handleMount}
      />
    </div>
  );
}
