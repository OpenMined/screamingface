// apps/desktop/src/renderer/src/lib/monaco-setup.ts
//
// Side-effect module: configure Monaco to run fully bundled (no CDN) so it works
// offline inside Electron. Import this once before mounting any Monaco editor.
//
// Python syntax highlighting is Monarch-based (shipped in monaco-editor's
// basic-languages) and needs only the base editor worker — no language server.
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

declare global {
  interface Window {
    MonacoEnvironment?: monaco.Environment;
  }
}

self.MonacoEnvironment = {
  getWorker(): Worker {
    return new EditorWorker();
  },
};

// Point @monaco-editor/react at the locally-bundled monaco instead of its
// default CDN loader.
loader.config({ monaco });
