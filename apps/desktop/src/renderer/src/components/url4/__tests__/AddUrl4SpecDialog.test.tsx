// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';
import { AddUrl4SpecDialog } from '../AddUrl4SpecDialog';

afterEach(cleanup);

it('creates a spec with the entered name', () => {
  const onCreate = vi.fn();
  render(<AddUrl4SpecDialog existingNames={['Alpha']} onClose={vi.fn()} onCreate={onCreate} />);
  fireEvent.change(screen.getByPlaceholderText(/my-ensemble/i), { target: { value: 'Beta' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));
  expect(onCreate).toHaveBeenCalledWith('Beta');
});

it('blocks an empty name', () => {
  const onCreate = vi.fn();
  render(<AddUrl4SpecDialog existingNames={[]} onClose={vi.fn()} onCreate={onCreate} />);
  expect(screen.getByRole('button', { name: 'Create' })).toHaveProperty('disabled', true);
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));
  expect(onCreate).not.toHaveBeenCalled();
});

it('blocks a duplicate name and shows a hint', () => {
  const onCreate = vi.fn();
  render(<AddUrl4SpecDialog existingNames={['Alpha']} onClose={vi.fn()} onCreate={onCreate} />);
  fireEvent.change(screen.getByPlaceholderText(/my-ensemble/i), { target: { value: 'Alpha' } });
  expect(screen.getByText(/already exists/i)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Create' })).toHaveProperty('disabled', true);
});
