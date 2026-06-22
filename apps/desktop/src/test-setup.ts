// test-setup.ts
// Expose `jest` as a compat alias for `vi` so that @testing-library/dom's
// jestFakeTimersAreEnabled() detection works correctly when vi.useFakeTimers()
// is active in tests.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).jest = (globalThis as any).vi;

// Polyfill ResizeObserver for jsdom (required by react-resizable-panels).
/* eslint-disable @typescript-eslint/no-explicit-any */
(globalThis as any).ResizeObserver =
  (globalThis as any).ResizeObserver ||
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
/* eslint-enable @typescript-eslint/no-explicit-any */

// Minimal default `window.electronAPI` so renderer components that call into the
// preload bridge during effects (e.g. LeaderboardLink → publish.getContext) don't
// throw in jsdom tests. Individual tests can override specific methods as needed.
/* eslint-disable @typescript-eslint/no-explicit-any */
if (typeof (globalThis as any).window !== 'undefined') {
  const win = (globalThis as any).window;
  win.electronAPI = win.electronAPI ?? {};
  win.electronAPI.publish = win.electronAPI.publish ?? {
    getContext: () =>
      Promise.resolve({
        scoreboardUrl: 'https://scoreboard.test',
        portalUrl: 'https://portal.test',
        client: { name: 'test', version: '0.0.0', platform: 'test' },
      }),
    openExternal: () => Promise.resolve(),
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */
