// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { it, expect, vi, afterEach, beforeEach } from 'vitest';
import { CopyButton } from '../CopyButton';

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  writeText.mockClear();
  Object.assign(navigator, { clipboard: { writeText } });
});
afterEach(cleanup);

it('copies its value to the clipboard on click', async () => {
  render(<CopyButton value="/claude()!hi" />);
  fireEvent.click(screen.getByRole('button', { name: /copy to clipboard/i }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith('/claude()!hi'));
});

it('shows a "Copied" affordance after copying', async () => {
  render(<CopyButton value="x" />);
  fireEvent.click(screen.getByRole('button', { name: /copy to clipboard/i }));
  await waitFor(() => expect(screen.getByRole('button').title).toBe('Copied'));
});
