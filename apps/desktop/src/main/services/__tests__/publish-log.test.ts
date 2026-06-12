import { vi, describe, it, expect, beforeEach } from 'vitest';

// debug-log imports electron's app at module load — stub the file sink.
const fileLog = vi.fn();
vi.mock('../../debug-log', () => ({ log: (m: string) => fileLog(m) }));

import { publishLog, getPublishLog, onPublishLog } from '../publish-log';

beforeEach(() => fileLog.mockClear());

describe('publish-log bus', () => {
  it('persists to the file sink and keeps an in-memory backlog', () => {
    publishLog('publish: hello');
    expect(fileLog).toHaveBeenCalledWith('publish: hello');
    const backlog = getPublishLog();
    expect(backlog[backlog.length - 1]).toContain('publish: hello');
  });

  it('notifies live subscribers and supports unsubscribe', () => {
    const seen: string[] = [];
    const off = onPublishLog((line) => seen.push(line));
    publishLog('publish: one');
    off();
    publishLog('publish: two');
    expect(seen.some((l) => l.includes('one'))).toBe(true);
    expect(seen.some((l) => l.includes('two'))).toBe(false);
  });
});
