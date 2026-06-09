// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { AddEvalRunDialog } from '../AddEvalRunDialog';

vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({ info: { scheme: 'http', host: 'localhost', port: 9100 } }),
}));
vi.mock('@/components/Url4Viewer', () => ({ Url4Viewer: () => <div data-testid="preview" /> }));

const fetchMock = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  (window as unknown as { electronAPI: unknown }).electronAPI = { server: { fetch: fetchMock } };
});

afterEach(() => {
  vi.useRealTimers();
});

const createBtn = () => screen.getByRole('button', { name: /create & run/i });

describe('AddEvalRunDialog', () => {
  it('enables Create only with a name and a server-validated url4 expression', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, body: '{"tokens":[]}' });
    const onCreate = vi.fn();
    render(<AddEvalRunDialog onClose={vi.fn()} onCreate={onCreate} />);

    expect(createBtn()).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('e.g. my-ensemble'), {
      target: { value: 'mine' },
    });
    fireEvent.change(screen.getByLabelText('URL4 expression'), {
      target: { value: '(x)!$prompt' },
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400); // debounce
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:9100/ensemble/highlight?q=' + encodeURIComponent('(x)!$prompt'),
    );
    expect(createBtn()).toBeEnabled();

    fireEvent.click(createBtn());
    expect(onCreate).toHaveBeenCalledWith({ spec: 'mine', expression: '(x)!$prompt' });
  });

  it('keeps Create disabled and shows the error when the expression fails validation', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 400, body: 'url4 parse error: bad' });
    render(<AddEvalRunDialog onClose={vi.fn()} onCreate={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('e.g. my-ensemble'), {
      target: { value: 'mine' },
    });
    fireEvent.change(screen.getByLabelText('URL4 expression'), { target: { value: 'bad((' } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(createBtn()).toBeDisabled();
    expect(screen.getByText(/parse error/i)).toBeInTheDocument();
  });
});
