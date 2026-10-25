import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import { globalIgnores } from 'eslint/config';
import eslintConfigPrettier from 'eslint-config-prettier';
import i18next from 'eslint-plugin-i18next';
import i18nextDefaults from 'eslint-plugin-i18next/lib/options/defaults.js';

export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactRefresh.configs.vite,
      eslintConfigPrettier,
    ],
    plugins: {
      'react-hooks': reactHooks,
    },
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Quality rules previously inherited from eslint-config-google
      'no-var': 'error',
      'prefer-const': ['error', { destructuring: 'all' }],
      'guard-for-in': 'error',
      'no-caller': 'error',
      'no-extend-native': 'error',
      'no-extra-bind': 'error',
      'no-multi-str': 'error',
      'no-new-wrappers': 'error',
      'no-throw-literal': 'error',
      'no-with': 'error',
      'prefer-promise-reject-errors': 'error',
      'prefer-rest-params': 'error',
      'prefer-spread': 'error',
      'no-array-constructor': 'error',
      camelcase: 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      'new-cap': 'off',
      // Disable the base no-unused-vars rule for TS files — it does not
      // understand type-only imports and produces false positives. The
      // TypeScript-aware version below handles all cases correctly.
      'no-unused-vars': 'off',
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      '@typescript-eslint/no-unused-vars': ['error', { varsIgnorePattern: '^_', argsIgnorePattern: '^_' }],
    },
  },
  {
    // User-visible text in pages and components goes through i18n (#9751):
    // literal JSX text, and literals in the attributes a user sees or a screen
    // reader announces, must be t('key', 'Default') with the key in every
    // locale. A real exception (a ticker placeholder, a brand name) takes a
    // disable-next-line comment for this rule with a reason; see
    // docs/CONTRIBUTING.md.
    files: ['src/pages/**/*.tsx', 'src/components/**/*.tsx'],
    ignores: ['**/*.test.tsx', '**/*.spec.tsx', '**/*.stories.tsx', '**/__tests__/**'],
    plugins: { i18next },
    rules: {
      'i18next/no-literal-string': [
        'error',
        {
          mode: 'jsx-only',
          'jsx-attributes': { include: ['title', 'label', 'placeholder', 'aria-label', 'alt'] },
          // Arguments and object values inside JSX are mostly keys, class
          // names and options (handleSort("pe_ratio"), { position: 'bottom' }).
          callees: { exclude: ['.*'] },
          'object-properties': { exclude: ['.*'] },
          // Keep the plugin's defaults (numbers, punctuation, CONSTANTS,
          // entities, emoji) and also allow text that is only symbols and
          // punctuation (sort and close glyphs such as ▲ ✕ ☰, "% (") and
          // upper-case ratio abbreviations (P/E, EV/EBITDA, LT D/E).
          words: {
            exclude: [...i18nextDefaults.words.exclude, /^[\s\p{P}\p{S}]+$/u, /^[A-Z]+(?:[ /][A-Z]+)+$/u],
          },
        },
      ],
    },
  },
]);
