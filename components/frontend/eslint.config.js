import prettierConfig from 'eslint-config-prettier/flat';
import prettierPlugin from 'eslint-plugin-prettier/recommended';
import sonarjs from 'eslint-plugin-sonarjs';
import unicorn from 'eslint-plugin-unicorn';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['dist']
  },
  prettierConfig,
  prettierPlugin,
  sonarjs.configs.recommended,
  unicorn.configs.recommended,
  {
    files: ['**/*.ts', '**/*.tsx'],
    extends: [
      ...tseslint.configs.strict,
      ...tseslint.configs.strictTypeChecked,
      ...tseslint.configs.stylistic,
      ...tseslint.configs.stylisticTypeChecked
    ],
    rules: {
      '@typescript-eslint/array-type': 'off',
      '@typescript-eslint/consistent-type-definitions': 'off',
      '@typescript-eslint/consistent-type-imports': [
        'warn',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' }
      ],
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/require-await': 'off',
      '@typescript-eslint/no-misused-promises': [
        'error',
        { checksVoidReturn: { attributes: false } }
      ],
      // Relax some rules for better developer experience
      '@typescript-eslint/prefer-nullish-coalescing': 'warn',
      '@typescript-eslint/no-floating-promises': 'warn',
      '@typescript-eslint/restrict-template-expressions': 'warn',
      '@typescript-eslint/no-unnecessary-condition': 'warn'
    }
  },
  {
    linterOptions: {
      reportUnusedDisableDirectives: true
    },
    languageOptions: {
      parserOptions: {
        projectService: true
      }
    }
  },
  {
    rules: {
      'unicorn/no-null': 'off',
      'unicorn/prevent-abbreviations': [
        'warn',
        {
          allowList: {
            db: true,
            ctx: true,
            e: true, // Allow 'e' for event handlers
            props: true,
            ref: true,
            err: true
          },
          ignore: [/env/i, /params/i, /util/i, /Props$/]
        }
      ],
      'unicorn/consistent-function-scoping': 'warn',
      'unicorn/no-nested-ternary': 'warn',
      // SonarJS - relax some rules
      'sonarjs/cognitive-complexity': 'warn',
      'sonarjs/no-nested-conditional': 'warn',
      'sonarjs/no-nested-template-literals': 'warn',
      'sonarjs/pseudo-random': 'off', // Allow Math.random() for non-security use
      'sonarjs/no-dead-store': 'warn',
      'sonarjs/no-unused-vars': 'warn',
      'sonarjs/unused-import': 'warn',
      'sonarjs/todo-tag': 'warn',
      'sonarjs/no-hardcoded-passwords': 'off' // False positives on API endpoint names
    }
  },
  {
    // The API client (formerly the published @syfthub/sdk) was written against a looser
    // ruleset. It is folded in as is; tighten these as its files are touched.
    files: ['src/lib/sdk/**/*.ts'],
    rules: {
      '@typescript-eslint/no-base-to-string': 'off',
      '@typescript-eslint/no-deprecated': 'off',
      '@typescript-eslint/no-invalid-void-type': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-unnecessary-type-parameters': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/return-await': 'off',
      'sonarjs/deprecation': 'off',
      'sonarjs/slow-regex': 'off',
      'sonarjs/void-use': 'off',
      'unicorn/prevent-abbreviations': 'off'
    }
  },
  {
    files: ['src/lib/sdk/__tests__/**/*.ts'],
    rules: {
      'sonarjs/no-clear-text-protocols': 'off' // test URLs point at http://localhost
    }
  }
);
