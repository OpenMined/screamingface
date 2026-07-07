// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { describe, it, expect, afterEach } from 'vitest';
import { LeaderboardTable } from '../LeaderboardTable';
import type { LeaderboardEntry } from '../../../../../preload/types';

const ENTRY: LeaderboardEntry = {
  rank: 1,
  specId: 'local-smoke',
  accuracy: 0.5,
  totalQuestions: 2,
  ranWithProviders: ['smoke'],
  submittedAt: '2026-07-07T15:30:05.108456Z',
  submittedBy: 'filip-local',
  verifiedByOpenmined: false,
  url4Expression: 'url4://smoke',
};

afterEach(cleanup);

describe('LeaderboardTable', () => {
  it('renders one row per entry with the expected columns', () => {
    render(<LeaderboardTable entries={[ENTRY]} />);
    expect(screen.getByText('local-smoke')).toBeInTheDocument();
    expect(screen.getByText('50.0%')).toBeInTheDocument();
    expect(screen.getByText('smoke')).toBeInTheDocument();
    expect(screen.getByText('filip-local')).toBeInTheDocument();
    expect(screen.getByText('url4://smoke')).toBeInTheDocument();
  });

  it('renders "—" for an anonymous (null submittedBy) entry', () => {
    render(<LeaderboardTable entries={[{ ...ENTRY, submittedBy: null }]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('marks a verified entry, and leaves an unverified one blank', () => {
    render(<LeaderboardTable entries={[{ ...ENTRY, verifiedByOpenmined: true }]} />);
    expect(screen.getByText('✓ verified')).toBeInTheDocument();
  });

  it('truncates a long url4 expression and keeps the full text in the title', () => {
    const long = 'url4://' + 'x'.repeat(100);
    render(<LeaderboardTable entries={[{ ...ENTRY, url4Expression: long }]} />);
    const cell = screen.getByTitle(long);
    expect(cell.textContent?.endsWith('…')).toBe(true);
    expect(cell.textContent?.length).toBeLessThan(long.length);
  });

  it('shows an empty-state message when there are no entries', () => {
    render(<LeaderboardTable entries={[]} />);
    expect(screen.getByText(/no submissions yet/i)).toBeInTheDocument();
  });
});
