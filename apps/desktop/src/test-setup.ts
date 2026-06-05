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
