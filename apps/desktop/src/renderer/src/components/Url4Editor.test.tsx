// @vitest-environment jsdom
import '@testing-library/jest-dom';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

// Mock Url4Viewer so the editor test never hits the highlight endpoint;
// echo the expression so we can assert the preview tracks the textarea.
vi.mock('@/components/Url4Viewer', () => ({
  Url4Viewer: ({ expression }: { expression: string }) => (
    <code data-testid="preview">{expression}</code>
  ),
}));

afterEach(cleanup);

import { Url4Editor } from './Url4Editor';

const initial = '/claude(hi)!answer';

it('prefills the textarea with the initial expression', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  expect(textarea.value).toBe(initial);
});

it('updates the live preview as the user types', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i);
  fireEvent.change(textarea, { target: { value: '/codex(yo)!answer' } });
  expect(screen.getByTestId('preview').textContent).toBe('/codex(yo)!answer');
});

it('Reset is disabled when unchanged and restores the original after edits', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const reset = screen.getByRole('button', { name: /reset/i });
  expect(reset).toBeDisabled();
  const textarea = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  fireEvent.change(textarea, { target: { value: 'edited' } });
  expect(reset).not.toBeDisabled();
  fireEvent.click(reset);
  expect(textarea.value).toBe(initial);
  expect(reset).toBeDisabled();
});

it('Re-run calls onRun with the current text', () => {
  const onRun = vi.fn();
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={onRun} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i);
  fireEvent.change(textarea, { target: { value: '/gemini(q)!a' } });
  fireEvent.click(screen.getByRole('button', { name: /re-run/i }));
  expect(onRun).toHaveBeenCalledWith('/gemini(q)!a');
});

it('Re-run is disabled when the expression is blank', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i);
  fireEvent.change(textarea, { target: { value: '   ' } });
  const rerun = screen.getByRole('button', { name: /re-run/i });
  expect(rerun).toBeDisabled();
});

it('re-seeds the textarea when the initial prop changes', () => {
  const { rerender } = render(
    <Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />,
  );
  const textarea = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  expect(textarea.value).toBe(initial);
  rerender(<Url4Editor initial="/codex(new)!q" serverUrl="http://x" onRun={vi.fn()} />);
  expect(textarea.value).toBe('/codex(new)!q');
});
