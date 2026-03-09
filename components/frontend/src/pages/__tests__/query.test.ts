import { describe, expect, it } from 'vitest';

import { parseQueryParameter } from '../query';

describe('parseQueryParam', () => {
  describe('valid inputs', () => {
    it('parses single data source with prompt', () => {
      const result = parseQueryParameter('openmined/wiki!what is federated learning');
      expect(result).toEqual({
        dataSources: ['openmined/wiki'],
        prompt: 'what is federated learning'
      });
    });

    it('parses multiple data sources with prompt', () => {
      const result = parseQueryParameter('openmined/wiki|openmined/news!what is FL');
      expect(result).toEqual({
        dataSources: ['openmined/wiki', 'openmined/news'],
        prompt: 'what is FL'
      });
    });

    it('parses model-only query (empty data sources)', () => {
      const result = parseQueryParameter('!hello world');
      expect(result).toEqual({
        dataSources: [],
        prompt: 'hello world'
      });
    });

    it('handles URL-encoded spaces (+ sign)', () => {
      // URLSearchParams decodes + as space before passing to parseQueryParam
      const result = parseQueryParameter('openmined/wiki!what is machine learning');
      expect(result).toEqual({
        dataSources: ['openmined/wiki'],
        prompt: 'what is machine learning'
      });
    });

    it('trims whitespace from slug parts', () => {
      const result = parseQueryParameter('openmined/wiki | openmined/news!test');
      expect(result).toEqual({
        dataSources: ['openmined/wiki', 'openmined/news'],
        prompt: 'test'
      });
    });

    it('handles prompt with exclamation marks after the first', () => {
      const result = parseQueryParameter('openmined/wiki!what is this!really');
      expect(result).toEqual({
        dataSources: ['openmined/wiki'],
        prompt: 'what is this!really'
      });
    });
  });

  describe('error cases', () => {
    it('returns error for null input', () => {
      const result = parseQueryParameter(null);
      expect('error' in result).toBe(true);
    });

    it('returns error for empty string', () => {
      const result = parseQueryParameter('');
      expect('error' in result).toBe(true);
    });

    it('returns error when no ! separator', () => {
      const result = parseQueryParameter('openmined/wiki');
      expect('error' in result).toBe(true);
      if ('error' in result) {
        expect(result.error).toMatch(/!/);
      }
    });

    it('returns error for empty prompt after !', () => {
      const result = parseQueryParameter('openmined/wiki!');
      expect('error' in result).toBe(true);
      if ('error' in result) {
        expect(result.error).toMatch(/[Ee]mpty/);
      }
    });

    it('returns error for prompt with only whitespace', () => {
      const result = parseQueryParameter('openmined/wiki!   ');
      expect('error' in result).toBe(true);
    });

    it('returns error for slug without / separator', () => {
      const result = parseQueryParameter('badslug!hello');
      expect('error' in result).toBe(true);
      if ('error' in result) {
        expect(result.error).toMatch(/badslug/);
      }
    });

    it('returns error for one invalid slug among valid ones', () => {
      const result = parseQueryParameter('openmined/wiki|badslug|openmined/news!hello');
      expect('error' in result).toBe(true);
      if ('error' in result) {
        expect(result.error).toMatch(/badslug/);
      }
    });
  });
});
