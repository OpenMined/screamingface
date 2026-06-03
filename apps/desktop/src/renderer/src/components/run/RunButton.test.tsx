// @vitest-environment jsdom
import '@testing-library/jest-dom';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { RunButton } from './RunButton';

afterEach(cleanup);

it('is enabled when idle and calls onRun', () => {
  const onRun = vi.fn();
  render(<RunButton state="idle" onRun={onRun} />);
  const btn = screen.getByRole('button', { name: /run locally/i });
  expect(btn).not.toBeDisabled();
  fireEvent.click(btn);
  expect(onRun).toHaveBeenCalledTimes(1);
});

it('is disabled while running', () => {
  render(<RunButton state="running" onRun={vi.fn()} />);
  expect(screen.getByRole('button')).toBeDisabled();
});

it('shows "Run again" label when done', () => {
  render(<RunButton state="done" onRun={vi.fn()} />);
  expect(screen.getByRole('button', { name: /run again/i })).not.toBeDisabled();
});
