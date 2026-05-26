import tsPlugin from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import sonarjsPlugin from 'eslint-plugin-sonarjs';

export default [
  {
    ignores: ['out/**', 'dist/**', 'node_modules/**'],
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      react: reactPlugin,
      'react-hooks': reactHooksPlugin,
      sonarjs: sonarjsPlugin,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...reactHooksPlugin.configs.recommended.rules,
      // sonarjs recommended set as warnings — baseline visibility, no commit blocking
      ...Object.fromEntries(
        Object.entries(sonarjsPlugin.configs.recommended.rules).map(([k, v]) => [
          k,
          Array.isArray(v) ? ['warn', ...v.slice(1)] : 'warn',
        ]),
      ),
      'react/react-in-jsx-scope': 'off',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      // Hard-enforced complexity gates — set at current high-water marks so
      // day 1 passes. See apps/desktop/docs/complexity-baseline.md for the
      // tightening roadmap.
      'sonarjs/cognitive-complexity': ['error', 34],
      'sonarjs/no-duplicate-string': ['error', { threshold: 31 }],
      'sonarjs/no-identical-functions': 'error',
      'sonarjs/no-collapsible-if': 'error',
    },
    settings: {
      react: { version: 'detect' },
    },
  },
];
