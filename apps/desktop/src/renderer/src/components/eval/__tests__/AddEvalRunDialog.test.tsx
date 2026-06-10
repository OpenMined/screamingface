// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { AddEvalRunDialog } from '../AddEvalRunDialog';

const serverFetch = vi.fn();
(window as unknown as { electronAPI: unknown }).electronAPI = {
  server: { fetch: serverFetch },
};

vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({ info: { scheme: 'http', host: 'localhost', port: 9100 } }),
}));
// Stub the Monaco url4 field with a labelled textarea so the dialog test stays
// in jsdom.
vi.mock('@/components/Url4Field', () => ({
  Url4Field: ({ value, onChange }: { value: string; onChange?: (v: string) => void }) => (
    <textarea
      aria-label="URL4 expression"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}));

const createBtn = () => screen.getByRole('button', { name: /create & run/i });

const SAVED_SPECS = {
  alpha: { expression: 'https://a.jsonl*(/claude($item.q)!$a)' },
  beta: { expression: '(b)!$prompt' },
};

beforeEach(() => {
  serverFetch.mockReset();
  serverFetch.mockResolvedValue({
    ok: true,
    body: JSON.stringify({ specs: SAVED_SPECS }),
  });
});

afterEach(() => {
  cleanup();
});

describe('AddEvalRunDialog', () => {
  it('enables Create only with a name and a non-empty expression', () => {
    const onCreate = vi.fn();
    render(<AddEvalRunDialog onClose={vi.fn()} onCreate={onCreate} />);
    expect(createBtn()).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('e.g. my-ensemble'), {
      target: { value: 'mine' },
    });
    expect(createBtn()).toBeDisabled(); // name only

    fireEvent.change(screen.getByLabelText('URL4 expression'), {
      target: { value: "https://x.jsonl*(/claude($item.q)!'a')" },
    });
    expect(createBtn()).toBeEnabled();
  });

  it('creates a run with the trimmed name + expression', () => {
    const onCreate = vi.fn();
    render(<AddEvalRunDialog onClose={vi.fn()} onCreate={onCreate} />);
    fireEvent.change(screen.getByPlaceholderText('e.g. my-ensemble'), {
      target: { value: '  mine  ' },
    });
    fireEvent.change(screen.getByLabelText('URL4 expression'), {
      target: { value: '  (x)!$prompt  ' },
    });
    fireEvent.click(createBtn());
    expect(onCreate).toHaveBeenCalledWith({ spec: 'mine', expression: '(x)!$prompt' });
  });

  it('opens the saved-spec picker and lists fetched specs', async () => {
    render(<AddEvalRunDialog onClose={vi.fn()} onCreate={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /choose from saved specs/i }));

    expect(await screen.findByText('Choose a saved spec')).toBeInTheDocument();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('beta')).toBeInTheDocument();
    expect(serverFetch).toHaveBeenCalledWith('http://localhost:9100/plugins/url4-specs/settings');
  });

  it('fills Name + expression when a spec is picked, then can create the run', async () => {
    const onCreate = vi.fn();
    render(<AddEvalRunDialog onClose={vi.fn()} onCreate={onCreate} />);
    fireEvent.click(screen.getByRole('button', { name: /choose from saved specs/i }));

    fireEvent.click(await screen.findByText('alpha'));

    // Picker closes, fields are populated.
    await waitFor(() => expect(screen.queryByText('Choose a saved spec')).not.toBeInTheDocument());
    const nameInput = screen.getByPlaceholderText('e.g. my-ensemble') as HTMLInputElement;
    const exprInput = screen.getByLabelText('URL4 expression') as HTMLTextAreaElement;
    expect(nameInput.value).toBe('alpha');
    expect(exprInput.value).toBe(SAVED_SPECS.alpha.expression);

    fireEvent.click(createBtn());
    expect(onCreate).toHaveBeenCalledWith({
      spec: 'alpha',
      expression: SAVED_SPECS.alpha.expression,
    });
  });

  it('changes nothing when the picker is cancelled', async () => {
    const onCreate = vi.fn();
    render(<AddEvalRunDialog onClose={vi.fn()} onCreate={onCreate} />);
    fireEvent.change(screen.getByPlaceholderText('e.g. my-ensemble'), {
      target: { value: 'keepme' },
    });

    fireEvent.click(screen.getByRole('button', { name: /choose from saved specs/i }));
    await screen.findByText('alpha');

    // Close the picker without selecting anything.
    fireEvent.click(screen.getByRole('button', { name: /close spec picker/i }));

    await waitFor(() => expect(screen.queryByText('Choose a saved spec')).not.toBeInTheDocument());
    const nameInput = screen.getByPlaceholderText('e.g. my-ensemble') as HTMLInputElement;
    expect(nameInput.value).toBe('keepme');
    expect(onCreate).not.toHaveBeenCalled();
  });
});
