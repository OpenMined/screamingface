// apps/desktop/src/renderer/src/lib/editor-height.ts
//
// Pure height-clamp for the url4 Monaco editor's auto-grow. Extracted so the cap
// logic is unit-testable without mounting Monaco. `maxContentHeight === null`
// means "no upper cap" — grow to the full content height (SF-309) so the editor
// never shows its own scrollbar inside a scrolling dialog.

const MIN_HEIGHT = 28;

export function clampEditorHeight(contentHeight: number, maxContentHeight: number | null): number {
  const lower = Math.max(contentHeight, MIN_HEIGHT);
  return maxContentHeight == null ? lower : Math.min(lower, maxContentHeight);
}
