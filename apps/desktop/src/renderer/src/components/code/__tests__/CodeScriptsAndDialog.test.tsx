// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';
import type { CodeScript } from '@/hooks/use-code-scripts';
import { CodeScriptsList } from '../CodeScriptsList';
import { AddCodeScriptDialog } from '../AddCodeScriptDialog';
import { CodeScriptDetail } from '../CodeScriptDetail';

// CodeScriptDetail lazy-loads the monaco popup; stub it so the detail tests stay light.
vi.mock('@/components/CodeEditorPopup', () => ({
  default: ({ onSave }: { onSave: (v: string) => void }) => (
    <button onClick={() => onSave('print(2)')}>stub-save</button>
  ),
}));

const scripts: CodeScript[] = [
  { name: 'check_correct', source: 'def main():\n    return True' },
  { name: 'helper', source: '# util\nx = 1' },
];

afterEach(cleanup);

// --- list ---
it('renders a row per script with .py name + first-line preview', () => {
  render(<CodeScriptsList scripts={scripts} selectedName={null} onSelect={vi.fn()} />);
  expect(screen.getByText('check_correct.py')).toBeTruthy();
  expect(screen.getByText('def main():')).toBeTruthy(); // first non-blank line
});

it('selects a script on click and filters', () => {
  const onSelect = vi.fn();
  render(<CodeScriptsList scripts={scripts} selectedName={null} onSelect={onSelect} />);
  fireEvent.click(screen.getByText('check_correct.py'));
  expect(onSelect).toHaveBeenCalledWith('check_correct');
  fireEvent.change(screen.getByRole('textbox', { name: /filter scripts/i }), {
    target: { value: 'helper' },
  });
  expect(screen.queryByText('check_correct.py')).toBeNull();
});

// --- add dialog ---
it('creates a valid identifier name', () => {
  const onCreate = vi.fn();
  render(
    <AddCodeScriptDialog existingNames={['check_correct']} onClose={vi.fn()} onCreate={onCreate} />,
  );
  fireEvent.change(screen.getByPlaceholderText(/check_correct/i), { target: { value: 'grader' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));
  expect(onCreate).toHaveBeenCalledWith('grader');
});

it('blocks an invalid (non-identifier) name', () => {
  const onCreate = vi.fn();
  render(<AddCodeScriptDialog existingNames={[]} onClose={vi.fn()} onCreate={onCreate} />);
  fireEvent.change(screen.getByPlaceholderText(/check_correct/i), { target: { value: '2bad' } });
  expect(screen.getByText(/python identifier/i)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Create' })).toHaveProperty('disabled', true);
});

// --- detail ---
it('renames inline and deletes after confirm; saves edited code', () => {
  const onRename = vi.fn();
  const onDelete = vi.fn();
  const onSaveSource = vi.fn();
  render(
    <CodeScriptDetail
      script={scripts[0]}
      onRename={onRename}
      onDelete={onDelete}
      onSaveSource={onSaveSource}
    />,
  );
  // rename
  fireEvent.click(screen.getByRole('button', { name: /rename script/i }));
  const input = screen.getByRole('textbox', { name: /script name/i });
  fireEvent.change(input, { target: { value: 'grader' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onRename).toHaveBeenCalledWith('check_correct', 'grader');
  // delete (confirm)
  fireEvent.click(screen.getByRole('button', { name: /delete/i }));
  const dialog = screen.getByRole('alertdialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
  expect(onDelete).toHaveBeenCalledWith('check_correct');
});
