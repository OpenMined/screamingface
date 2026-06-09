// @vitest-environment jsdom
import '@testing-library/jest-dom';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

// Stub the Monaco url4 field with a plain textarea so the editor test stays in
// jsdom and never loads Monaco / hits the highlight endpoint.
vi.mock('@/components/Url4Field', () => ({
  Url4Field: ({ value, onChange }: { value: string; onChange?: (v: string) => void }) => (
    <textarea
      aria-label="URL4 expression editor"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}));

afterEach(cleanup);

import { Url4Editor } from './Url4Editor';

const initial = '/claude(hi)!answer';

it('prefills the editor with the initial expression', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const field = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  expect(field.value).toBe(initial);
});

it('Reset is disabled when unchanged and restores the original after edits', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const reset = screen.getByRole('button', { name: /reset/i });
  expect(reset).toBeDisabled();
  const field = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  fireEvent.change(field, { target: { value: 'edited' } });
  expect(reset).not.toBeDisabled();
  fireEvent.click(reset);
  expect(field.value).toBe(initial);
  expect(reset).toBeDisabled();
});

it('Re-run calls onRun with the current text', () => {
  const onRun = vi.fn();
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={onRun} />);
  fireEvent.change(screen.getByLabelText(/url4 expression editor/i), {
    target: { value: '/gemini(q)!a' },
  });
  fireEvent.click(screen.getByRole('button', { name: /re-run/i }));
  expect(onRun).toHaveBeenCalledWith('/gemini(q)!a');
});

it('Re-run is disabled when the expression is blank', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  fireEvent.change(screen.getByLabelText(/url4 expression editor/i), { target: { value: '   ' } });
  expect(screen.getByRole('button', { name: /re-run/i })).toBeDisabled();
});

it('re-seeds when the initial prop changes', () => {
  const { rerender } = render(
    <Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />,
  );
  const field = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  expect(field.value).toBe(initial);
  rerender(<Url4Editor initial="/codex(new)!q" serverUrl="http://x" onRun={vi.fn()} />);
  expect(field.value).toBe('/codex(new)!q');
});
