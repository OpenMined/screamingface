// test-setup.ts
// Expose `jest` as a compat alias for `vi` so that @testing-library/dom's
// jestFakeTimersAreEnabled() detection works correctly when vi.useFakeTimers()
// is active in tests.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).jest = (globalThis as any).vi;
