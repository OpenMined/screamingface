// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';

vi.mock('@/hooks/use-url4-specs', () => ({
  useUrl4Specs: () => ({
    specs: [],
    loading: false,
    error: null,
    createSpec: vi.fn(),
    renameSpec: vi.fn(),
    deleteSpec: vi.fn(),
    saveExpression: vi.fn(),
  }),
}));
// Detail pulls in monaco via Url4Field/CodeEditorPopup — stub it out.
vi.mock('@/components/url4/Url4SpecDetail', () => ({ Url4SpecDetail: () => null }));

afterEach(cleanup);

import { Url4StudioView } from './Url4StudioView';

it('renders header, New spec, both pane toggles, and the empty state', () => {
  render(<Url4StudioView />);
  expect(screen.getByText('URL4 Studio')).toBeTruthy();
  expect(screen.getByRole('button', { name: /new spec/i })).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide specs list/i })).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide spec details/i })).toBeTruthy();
  expect(screen.getByText('Select a spec to see details')).toBeTruthy();
});
