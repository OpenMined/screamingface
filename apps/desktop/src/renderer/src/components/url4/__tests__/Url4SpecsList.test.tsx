// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';
import type { Url4Spec } from '@/hooks/use-url4-specs';
import { Url4SpecsList } from '../Url4SpecsList';

const specs: Url4Spec[] = [
  { name: 'Alpha', expression: '/claude()!hi' },
  { name: 'Beta', expression: '/codex()!yo' },
];

afterEach(cleanup);

it('renders a row per spec with name + expression preview', () => {
  render(<Url4SpecsList specs={specs} selectedName={null} onSelect={vi.fn()} />);
  expect(screen.getByText('Alpha')).toBeTruthy();
  expect(screen.getByText('/claude()!hi')).toBeTruthy();
  expect(screen.getByText('Beta')).toBeTruthy();
});

it('selects a spec on row click', () => {
  const onSelect = vi.fn();
  render(<Url4SpecsList specs={specs} selectedName={null} onSelect={onSelect} />);
  fireEvent.click(screen.getByText('Alpha'));
  expect(onSelect).toHaveBeenCalledWith('Alpha');
});

it('filters by name/expression', () => {
  render(<Url4SpecsList specs={specs} selectedName={null} onSelect={vi.fn()} />);
  fireEvent.change(screen.getByRole('textbox', { name: /filter specs/i }), {
    target: { value: 'codex' },
  });
  expect(screen.queryByText('Alpha')).toBeNull();
  expect(screen.getByText('Beta')).toBeTruthy();
});

it('shows the empty state when there are no specs', () => {
  render(<Url4SpecsList specs={[]} selectedName={null} onSelect={vi.fn()} />);
  expect(screen.getByText(/no url4 specs yet/i)).toBeTruthy();
});
