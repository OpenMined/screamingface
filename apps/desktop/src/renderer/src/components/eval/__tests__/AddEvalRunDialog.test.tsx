// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { AddEvalRunDialog } from '../AddEvalRunDialog';

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
});
