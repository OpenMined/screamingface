// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';

vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({ info: { scheme: 'http', host: 'localhost', port: 8000 } }),
}));
vi.mock('@/components/Url4Field', () => ({
  Url4Field: ({ value }: { value: string }) => <span data-testid="url4">{value}</span>,
}));
// CodeEditorPopup is lazy + monaco-heavy — stub it to a Save button that emits a value.
vi.mock('@/components/CodeEditorPopup', () => ({
  default: ({ onSave }: { onSave: (v: string) => void }) => (
    <button onClick={() => onSave('/codex()!edited')}>stub-save</button>
  ),
}));

afterEach(cleanup);

import { Url4SpecDetail } from '../Url4SpecDetail';

const spec = { name: 'Alpha', expression: '/claude()!hi' };

it('renders the name and read-only expression', () => {
  render(
    <Url4SpecDetail spec={spec} onRename={vi.fn()} onDelete={vi.fn()} onSaveExpression={vi.fn()} />,
  );
  expect(screen.getByText('Alpha')).toBeTruthy();
  expect(screen.getByTestId('url4').textContent).toBe('/claude()!hi');
});

it('renames inline on Enter', () => {
  const onRename = vi.fn();
  render(
    <Url4SpecDetail
      spec={spec}
      onRename={onRename}
      onDelete={vi.fn()}
      onSaveExpression={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /rename spec/i }));
  const input = screen.getByRole('textbox', { name: /spec name/i });
  fireEvent.change(input, { target: { value: 'Renamed' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onRename).toHaveBeenCalledWith('Alpha', 'Renamed');
});

it('deletes only after confirming', () => {
  const onDelete = vi.fn();
  render(
    <Url4SpecDetail
      spec={spec}
      onRename={vi.fn()}
      onDelete={onDelete}
      onSaveExpression={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /delete/i }));
  expect(onDelete).not.toHaveBeenCalled();
  const dialog = screen.getByRole('alertdialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
  expect(onDelete).toHaveBeenCalledWith('Alpha');
});

it('saves an edited expression from the popup', async () => {
  const onSaveExpression = vi.fn();
  render(
    <Url4SpecDetail
      spec={spec}
      onRename={vi.fn()}
      onDelete={vi.fn()}
      onSaveExpression={onSaveExpression}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /edit expression/i }));
  const saveBtn = await screen.findByText('stub-save');
  fireEvent.click(saveBtn);
  await waitFor(() => expect(onSaveExpression).toHaveBeenCalledWith('Alpha', '/codex()!edited'));
});
