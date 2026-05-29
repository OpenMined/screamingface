// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react';
import { describe, it, expect, afterEach } from 'vitest';
import { RunProgress } from './RunProgress';
import type { EvalRunDetail } from '@/components/eval/types';

afterEach(cleanup);

const base: EvalRunDetail = {
  id: 'r1',
  spec_name: 'HLE',
  url4_expression: 'x',
  started_at: '',
  finished_at: null,
  status: 'running',
  accuracy: null,
  total_questions: 4,
  correct_questions: 2,
  error: null,
  questions: [],
};

it('renders correct/total progress', () => {
  render(<RunProgress run={base} />);
  expect(screen.getByText(/2\s*\/\s*4/)).toBeTruthy();
});

it('renders a placeholder when counts are not yet known', () => {
  render(<RunProgress run={{ ...base, total_questions: null, correct_questions: null }} />);
  expect(screen.getByText(/starting/i)).toBeTruthy();
});

it('renders nothing when run is null', () => {
  const { container } = render(<RunProgress run={null} />);
  expect(container.textContent).toBe('');
});
