import { describe, expect, it } from 'vitest';

import { buildSnippet, sampleFilter } from '@/components/endpoint/api-tab';

const filters = {
  fields: {
    published: { type: 'datetime', ops: ['gte', 'lt'] },
    tags: { type: 'string[]', ops: ['contains_any'] }
  },
  logic: ['and', 'or'],
  max_depth: 5,
  max_conditions: 50,
  max_list_values: 100
};

describe('sampleFilter', () => {
  it('writes the first filterable field with its first operator', () => {
    expect(sampleFilter(filters)).toBe('F("published") >= "2026-01-01"');
    expect(sampleFilter({ ...filters, fields: { tags: filters.fields.tags } })).toBe(
      'F("tags").contains_any(["value"])'
    );
    expect(sampleFilter({ ...filters, fields: { n: { type: 'number', ops: ['between'] } } })).toBe(
      'F("n").op("between", 0)'
    );
  });

  it('is null without a schema or without filterable fields', () => {
    expect(sampleFilter(null)).toBeNull();
    expect(sampleFilter({ ...filters, fields: {} })).toBeNull();
  });
});

describe('buildSnippet', () => {
  it('narrows the search when the endpoint publishes filters', () => {
    const code = buildSnippet('alice/feed', true, filters);
    expect(code).toContain('from syfthub import F');
    expect(code).toContain('source.where(F("published") >= "2026-01-01")');
  });

  it('names the path alone when there is nothing to filter on', () => {
    const code = buildSnippet('alice/feed', true, null);
    expect(code).not.toContain('from syfthub import F');
    expect(code).toContain('hub.search("Hello, world!", ["alice/feed"])');
  });
});
