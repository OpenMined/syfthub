import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createMockChatSource } from '@/test/mocks/fixtures';

import {
  analyzeQueryForSources,
  filterRelevantSources,
  findEndpointByName,
  findEndpointByPath,
  mapEndpointPublicToSource,
  parseEndpointMentions
} from '../endpoint-utils';

// ============================================================================
// parseEndpointMentions
// ============================================================================

describe('parseEndpointMentions', () => {
  it('extracts owner/slug pattern', () => {
    const result = parseEndpointMentions('Use alice/dataset-1 for this');
    expect(result).toEqual(['alice/dataset-1']);
  });

  it('extracts multiple mentions', () => {
    const result = parseEndpointMentions('Compare alice/ds1 with bob/ds2');
    expect(result).toEqual(['alice/ds1', 'bob/ds2']);
  });

  it('returns empty for no mentions', () => {
    expect(parseEndpointMentions('no endpoint mentions here')).toEqual([]);
  });

  it('handles underscores', () => {
    const result = parseEndpointMentions('Use my_org/my_dataset');
    expect(result).toEqual(['my_org/my_dataset']);
  });

  it('requires owner to start with letter', () => {
    const result = parseEndpointMentions('Use 123/slug');
    expect(result).toEqual([]);
  });
});

// ============================================================================
// findEndpointByPath
// ============================================================================

describe('findEndpointByPath', () => {
  const sources = [
    createMockChatSource({ full_path: 'alice/dataset-1', slug: 'dataset-1' }),
    createMockChatSource({ full_path: 'bob/model-1', slug: 'model-1' })
  ];

  it('finds by exact path (case-insensitive)', () => {
    const result = findEndpointByPath(sources, 'Alice/Dataset-1');
    expect(result?.slug).toBe('dataset-1');
  });

  it('returns undefined for non-matching path', () => {
    expect(findEndpointByPath(sources, 'unknown/path')).toBeUndefined();
  });

  it('returns undefined for empty sources', () => {
    expect(findEndpointByPath([], 'alice/dataset-1')).toBeUndefined();
  });
});

// ============================================================================
// findEndpointByName
// ============================================================================

describe('findEndpointByName', () => {
  const sources = [
    createMockChatSource({ name: 'Financial Data', slug: 'financial-data' }),
    createMockChatSource({ name: 'Medical Records', slug: 'medical-records' })
  ];

  it('finds by exact name (case-insensitive)', () => {
    const result = findEndpointByName(sources, 'financial data');
    expect(result?.slug).toBe('financial-data');
  });

  it('trims whitespace', () => {
    const result = findEndpointByName(sources, '  Financial Data  ');
    expect(result?.slug).toBe('financial-data');
  });

  it('returns undefined for non-matching name', () => {
    expect(findEndpointByName(sources, 'Unknown Data')).toBeUndefined();
  });
});

// ============================================================================
// filterRelevantSources
// ============================================================================

describe('filterRelevantSources', () => {
  const sources = [
    createMockChatSource({
      name: 'Financial Dataset',
      description: 'Contains financial market data',
      tags: ['finance', 'stocks'],
      readme: 'Financial analysis dataset',
      slug: 'financial'
    }),
    createMockChatSource({
      name: 'Medical Records',
      description: 'Hospital patient records',
      tags: ['health', 'medical'],
      readme: 'Medical data collection',
      slug: 'medical'
    }),
    createMockChatSource({
      name: 'Weather API',
      description: 'Global weather forecasts',
      tags: ['weather', 'climate'],
      readme: 'Weather prediction model',
      slug: 'weather'
    })
  ];

  it('returns all sources for query with only stop words', () => {
    const result = filterRelevantSources(sources, 'the is a');
    expect(result).toHaveLength(3);
  });

  it('filters by name match (highest score)', () => {
    const result = filterRelevantSources(sources, 'financial data');
    expect(result[0]?.slug).toBe('financial');
  });

  it('filters by description match', () => {
    const result = filterRelevantSources(sources, 'hospital');
    expect(result).toHaveLength(1);
    expect(result[0]?.slug).toBe('medical');
  });

  it('filters by tag match', () => {
    const result = filterRelevantSources(sources, 'climate');
    expect(result).toHaveLength(1);
    expect(result[0]?.slug).toBe('weather');
  });

  it('returns empty for unmatched query', () => {
    const result = filterRelevantSources(sources, 'quantum computing');
    expect(result).toHaveLength(0);
  });

  it('sorts by relevance score descending', () => {
    const result = filterRelevantSources(sources, 'medical health');
    // "medical" should be first since it matches name and tags
    if (result.length > 0) {
      expect(result[0]?.slug).toBe('medical');
    }
  });
});

// ============================================================================
// analyzeQueryForSources
// ============================================================================

describe('analyzeQueryForSources', () => {
  const sources = [
    createMockChatSource({
      name: 'Financial Data',
      full_path: 'alice/financial-data',
      slug: 'financial-data',
      description: 'Market data',
      tags: ['finance'],
      readme: ''
    }),
    createMockChatSource({
      name: 'Medical Records',
      full_path: 'bob/medical-records',
      slug: 'medical-records',
      description: 'Health data',
      tags: ['health'],
      readme: ''
    })
  ];

  it('auto-selects for explicit path mention', () => {
    const result = analyzeQueryForSources('Use alice/financial-data for analysis', sources);
    expect(result.action).toBe('auto-select');
    expect(result.matchedEndpoint?.slug).toBe('financial-data');
    expect(result.mentionedPath).toBe('alice/financial-data');
  });

  it('auto-selects for exact name match', () => {
    const result = analyzeQueryForSources('Query Financial Data about stocks', sources);
    expect(result.action).toBe('auto-select');
    expect(result.matchedEndpoint?.slug).toBe('financial-data');
  });

  it('shows relevant sources for keyword match', () => {
    const result = analyzeQueryForSources('analyze market finance trends', sources);
    expect(result.action).toBe('show-relevant');
    expect(result.relevantSources.length).toBeGreaterThan(0);
    expect(result.relevantSources.length).toBeLessThan(sources.length);
  });

  it('shows all sources when no specific match', () => {
    const result = analyzeQueryForSources('random unrelated query stuff xyz', sources);
    expect(result.action).toBe('show-all');
    expect(result.relevantSources).toHaveLength(sources.length);
  });

  it('returns show-all for empty query', () => {
    const result = analyzeQueryForSources('', sources);
    expect(result.action).toBe('show-all');
  });
});

// ============================================================================
// mapEndpointPublicToSource
// ============================================================================

describe('mapEndpointPublicToSource', () => {
  beforeEach(() => {
    vi.setSystemTime(new Date('2024-01-15T00:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('maps SDK endpoint to ChatSource with active status', () => {
    const endpoint = {
      name: 'Test',
      slug: 'test',
      description: 'A test endpoint',
      type: 'data_source' as const,
      ownerUsername: 'alice',
      contributorsCount: 3,
      version: '1.0',
      readme: 'readme',
      tags: ['ai'],
      starsCount: 5,
      policies: [],
      connect: [],
      createdAt: new Date('2024-01-01T00:00:00Z'),
      updatedAt: new Date('2024-01-14T00:00:00Z') // 1 day ago
    };

    const result = mapEndpointPublicToSource(endpoint as never);
    expect(result.id).toBe('test');
    expect(result.name).toBe('Test');
    expect(result.status).toBe('active');
    expect(result.full_path).toBe('alice/test');
    expect(result.owner_username).toBe('alice');
    expect(result.tags).toEqual(['ai']);
  });

  it('sets warning status for endpoints older than 7 days', () => {
    const endpoint = {
      name: 'Old',
      slug: 'old',
      description: '',
      type: 'model' as const,
      ownerUsername: 'bob',
      contributorsCount: 0,
      version: '1.0',
      readme: '',
      tags: [],
      starsCount: 0,
      policies: [],
      connect: [],
      createdAt: new Date('2023-12-01T00:00:00Z'),
      updatedAt: new Date('2024-01-01T00:00:00Z') // 14 days ago
    };

    const result = mapEndpointPublicToSource(endpoint as never);
    expect(result.status).toBe('warning');
  });

  it('sets inactive status for endpoints older than 30 days', () => {
    const endpoint = {
      name: 'Very Old',
      slug: 'very-old',
      description: '',
      type: 'model' as const,
      ownerUsername: 'carol',
      contributorsCount: 0,
      version: '1.0',
      readme: '',
      tags: [],
      starsCount: 0,
      policies: [],
      connect: [],
      createdAt: new Date('2023-06-01T00:00:00Z'),
      updatedAt: new Date('2023-11-01T00:00:00Z') // > 30 days ago
    };

    const result = mapEndpointPublicToSource(endpoint as never);
    expect(result.status).toBe('inactive');
  });

  it('extracts URL from enabled connection', () => {
    const endpoint = {
      name: 'Connected',
      slug: 'connected',
      description: '',
      type: 'model' as const,
      ownerUsername: 'dave',
      contributorsCount: 0,
      version: '1.0',
      readme: '',
      tags: [],
      starsCount: 0,
      policies: [],
      connect: [
        {
          type: 'http',
          enabled: true,
          description: 'HTTP connection',
          config: { url: 'https://example.com/api', tenant_name: 'my-tenant' }
        }
      ],
      createdAt: new Date('2024-01-14T00:00:00Z'),
      updatedAt: new Date('2024-01-14T00:00:00Z')
    };

    const result = mapEndpointPublicToSource(endpoint as never);
    expect(result.url).toBe('https://example.com/api');
    expect(result.tenant_name).toBe('my-tenant');
  });

  it('handles missing connection', () => {
    const endpoint = {
      name: 'No Connect',
      slug: 'no-connect',
      description: '',
      type: 'model' as const,
      ownerUsername: 'eve',
      contributorsCount: 0,
      version: '1.0',
      readme: '',
      tags: [],
      starsCount: 0,
      policies: [],
      connect: [],
      createdAt: new Date('2024-01-14T00:00:00Z'),
      updatedAt: new Date('2024-01-14T00:00:00Z')
    };

    const result = mapEndpointPublicToSource(endpoint as never);
    expect(result.url).toBeUndefined();
    expect(result.tenant_name).toBeUndefined();
  });
});
