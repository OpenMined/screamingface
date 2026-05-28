import { resolve } from 'path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer/src'),
    },
  },
  test: {
    // Default to node; per-file pragma `// @vitest-environment jsdom` opts in for renderer tests.
    environment: 'node',
    // Expose `jest` as a compat alias so @testing-library/dom's
    // jestFakeTimersAreEnabled() detection works with vi.useFakeTimers().
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
});
