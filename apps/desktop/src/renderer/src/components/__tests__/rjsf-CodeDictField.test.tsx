// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import type { FieldProps } from '@rjsf/utils';
import { CodeDictField } from '../rjsf-CodeDictField';

// Stub the lazy Monaco popup so jsdom never loads monaco-editor.
vi.mock('@/components/CodeEditorPopup', () => ({
  default: ({ title }: { title: string }) => <div data-testid="popup">{title}</div>,
}));

function makeProps(
  formData: Record<string, string>,
  onChange = vi.fn(),
): { props: FieldProps; onChange: ReturnType<typeof vi.fn> } {
  const props = {
    formData,
    onChange,
    uiSchema: { 'ui:options': { language: 'python' } },
    schema: { type: 'object' },
  } as unknown as FieldProps;
  return { props, onChange };
}

describe('CodeDictField', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists existing scripts as <name>.py', () => {
    const { props } = makeProps({ check: 'print(1)', score: '' });
    render(<CodeDictField {...props} />);
    expect(screen.getByText('check.py')).toBeInTheDocument();
    expect(screen.getByText('score.py')).toBeInTheDocument();
  });

  it('rejects an invalid script name and does not mutate', () => {
    const { props, onChange } = makeProps({ check: 'x' });
    render(<CodeDictField {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /add script/i }));
    fireEvent.change(screen.getByPlaceholderText('script_name'), { target: { value: '1bad' } });
    fireEvent.click(screen.getByRole('button', { name: /^Add$/ }));
    expect(screen.getByText(/python identifier/i)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('adds a valid new script via onChange', async () => {
    const { props, onChange } = makeProps({ check: 'x' });
    render(<CodeDictField {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /add script/i }));
    fireEvent.change(screen.getByPlaceholderText('script_name'), {
      target: { value: 'calc_score' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Add$/ }));
    expect(onChange).toHaveBeenCalledWith({ check: 'x', calc_score: '' });
    // Adding immediately opens the editor popup for the new script.
    expect(await screen.findByTestId('popup')).toHaveTextContent('calc_score.py');
  });

  it('deletes a script via onChange', () => {
    const { props, onChange } = makeProps({ check: 'x', score: 'y' });
    render(<CodeDictField {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /delete check/i }));
    expect(onChange).toHaveBeenCalledWith({ score: 'y' });
  });

  it('opens the Monaco popup when a script is clicked', async () => {
    const { props } = makeProps({ check: 'print(1)' });
    render(<CodeDictField {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'check.py' }));
    expect(await screen.findByTestId('popup')).toHaveTextContent('check.py');
  });
});
