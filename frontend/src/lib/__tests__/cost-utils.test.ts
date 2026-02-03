import { describe, expect, it } from 'vitest';

import { createMockChatSource } from '@/test/mocks/fixtures';

import {
  calculateDataSourceCost,
  calculateFullCostBreakdown,
  calculateModelCost,
  estimatePerRequestCost,
  extractCostsFromPolicy,
  extractTransactionPolicy,
  formatCostPerUnit,
  formatCurrency,
  formatPerRequestCost,
  formatTokenCount,
  getCostPercentage,
  getCostsFromSource
} from '../cost-utils';

// ============================================================================
// extractTransactionPolicy
// ============================================================================

describe('extractTransactionPolicy', () => {
  it('returns null for undefined policies', () => {
    expect(extractTransactionPolicy()).toBeNull();
  });

  it('returns null for empty array', () => {
    expect(extractTransactionPolicy([])).toBeNull();
  });

  it('returns null when no transaction policy exists', () => {
    expect(
      extractTransactionPolicy([
        { type: 'rate_limit', version: '1.0', enabled: true, description: '', config: {} }
      ])
    ).toBeNull();
  });

  it('returns the enabled transaction policy', () => {
    const policy = {
      type: 'transaction',
      version: '1.0',
      enabled: true,
      description: 'Transaction policy',
      config: { costs: { inputTokens: 0.001, outputTokens: 0.002, currency: 'USD' } }
    };
    expect(extractTransactionPolicy([policy])).toEqual(policy);
  });

  it('ignores disabled transaction policies', () => {
    const policy = {
      type: 'transaction',
      version: '1.0',
      enabled: false,
      description: '',
      config: {}
    };
    expect(extractTransactionPolicy([policy])).toBeNull();
  });

  it('is case-insensitive on type', () => {
    const policy = {
      type: 'Transaction',
      version: '1.0',
      enabled: true,
      description: '',
      config: {}
    };
    expect(extractTransactionPolicy([policy])).toEqual(policy);
  });
});

// ============================================================================
// extractCostsFromPolicy
// ============================================================================

describe('extractCostsFromPolicy', () => {
  it('returns defaults for null policy', () => {
    expect(extractCostsFromPolicy(null)).toEqual({
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });

  it('returns defaults for policy without config', () => {
    const policy = {
      type: 'transaction',
      version: '1.0',
      enabled: true,
      description: '',
      config: {}
    };
    expect(extractCostsFromPolicy(policy)).toEqual({
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });

  it('extracts costs from policy config', () => {
    const policy = {
      type: 'transaction',
      version: '1.0',
      enabled: true,
      description: '',
      config: { costs: { inputTokens: 0.001, outputTokens: 0.002, currency: 'EUR' } }
    };
    expect(extractCostsFromPolicy(policy)).toEqual({
      inputPerToken: 0.001,
      outputPerToken: 0.002,
      currency: 'EUR',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });

  it('extracts per-call pricing from policy config', () => {
    const policy = {
      type: 'accounting',
      version: '1.0',
      enabled: true,
      description: 'Per-call pricing',
      config: { pricingMode: 'per_call', price: 0.05, currency: 'USD' }
    };
    expect(extractCostsFromPolicy(policy)).toEqual({
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_call',
      pricePerCall: 0.05
    });
  });

  it('falls back to per-token when pricingMode is per_call but price is missing', () => {
    const policy = {
      type: 'accounting',
      version: '1.0',
      enabled: true,
      description: '',
      config: { pricingMode: 'per_call' }
    };
    expect(extractCostsFromPolicy(policy)).toEqual({
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });
});

// ============================================================================
// getCostsFromSource
// ============================================================================

describe('getCostsFromSource', () => {
  it('returns zero costs for null source', () => {
    expect(getCostsFromSource(null)).toEqual({
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });

  it('returns zero costs for source without policies', () => {
    const source = createMockChatSource({ policies: undefined });
    expect(getCostsFromSource(source)).toEqual({
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });

  it('extracts costs from source with transaction policy', () => {
    const source = createMockChatSource({
      policies: [
        {
          type: 'transaction',
          version: '1.0',
          enabled: true,
          description: '',
          config: { costs: { inputTokens: 0.01, outputTokens: 0.02, currency: 'USD' } }
        }
      ]
    });
    expect(getCostsFromSource(source)).toEqual({
      inputPerToken: 0.01,
      outputPerToken: 0.02,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });

  it('extracts costs from source with accounting policy', () => {
    const source = createMockChatSource({
      policies: [
        {
          type: 'accounting',
          version: '1.0',
          enabled: true,
          description: '',
          config: { costs: { inputTokens: 0.005, outputTokens: 0.01, currency: 'USD' } }
        }
      ]
    });
    expect(getCostsFromSource(source)).toEqual({
      inputPerToken: 0.005,
      outputPerToken: 0.01,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    });
  });

  it('extracts per-call costs from source with accounting policy', () => {
    const source = createMockChatSource({
      policies: [
        {
          type: 'accounting',
          version: '1.0',
          enabled: true,
          description: '',
          config: { pricingMode: 'per_call', price: 0.1 }
        }
      ]
    });
    expect(getCostsFromSource(source)).toEqual({
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_call',
      pricePerCall: 0.1
    });
  });
});

// ============================================================================
// calculateModelCost
// ============================================================================

describe('calculateModelCost', () => {
  const params = { estimatedInputTokens: 500, estimatedOutputTokens: 1000, queriesPerSource: 1 };

  it('returns null for null source', () => {
    expect(calculateModelCost(null, params)).toBeNull();
  });

  it('calculates cost from token estimates', () => {
    const source = createMockChatSource({
      policies: [
        {
          type: 'transaction',
          version: '1.0',
          enabled: true,
          description: '',
          config: { costs: { inputTokens: 0.001, outputTokens: 0.002, currency: 'USD' } }
        }
      ]
    });
    const result = calculateModelCost(source, params);
    expect(result).not.toBeNull();
    expect(result?.inputCost).toBeCloseTo(0.5); // 500 * 0.001
    expect(result?.outputCost).toBeCloseTo(2); // 1000 * 0.002
    expect(result?.totalCost).toBeCloseTo(2.5);
    expect(result?.hasPolicy).toBe(true);
  });

  it('sets hasPolicy false when no cost config', () => {
    const source = createMockChatSource({ policies: [] });
    const result = calculateModelCost(source, params);
    expect(result?.hasPolicy).toBe(false);
  });

  it('calculates flat cost for per-call pricing', () => {
    const source = createMockChatSource({
      name: 'GPT-4 Code Helper',
      slug: 'gpt-4-code-helper',
      policies: [
        {
          type: 'accounting',
          version: '1.0',
          enabled: true,
          description: '',
          config: { pricingMode: 'per_call', price: 0.05 }
        }
      ]
    });
    const result = calculateModelCost(source, params);
    expect(result).not.toBeNull();
    expect(result?.inputCost).toBe(0);
    expect(result?.outputCost).toBe(0);
    expect(result?.totalCost).toBe(0.05);
    expect(result?.hasPolicy).toBe(true);
    expect(result?.pricingMode).toBe('per_call');
  });
});

// ============================================================================
// calculateDataSourceCost
// ============================================================================

describe('calculateDataSourceCost', () => {
  const params = { estimatedInputTokens: 500, estimatedOutputTokens: 1000, queriesPerSource: 1 };

  it('calculates zero cost for source without pricing', () => {
    const source = createMockChatSource();
    const result = calculateDataSourceCost(source, params);
    expect(result.totalCost).toBe(0);
    expect(result.hasPolicy).toBe(false);
  });
});

// ============================================================================
// calculateFullCostBreakdown
// ============================================================================

describe('calculateFullCostBreakdown', () => {
  it('returns empty breakdown for null model and no data sources', () => {
    const result = calculateFullCostBreakdown(null, []);
    expect(result.totalCost).toBe(0);
    expect(result.hasAnyPricing).toBe(false);
    expect(result.model).toBeNull();
    expect(result.dataSources).toEqual([]);
  });

  it('aggregates model and data source costs', () => {
    const model = createMockChatSource({
      name: 'GPT',
      slug: 'gpt',
      policies: [
        {
          type: 'transaction',
          version: '1.0',
          enabled: true,
          description: '',
          config: { costs: { inputTokens: 0.001, outputTokens: 0.002, currency: 'USD' } }
        }
      ]
    });
    const ds = createMockChatSource({
      name: 'DS',
      slug: 'ds',
      policies: [
        {
          type: 'transaction',
          version: '1.0',
          enabled: true,
          description: '',
          config: { costs: { inputTokens: 0.0005, outputTokens: 0.001, currency: 'USD' } }
        }
      ]
    });
    const result = calculateFullCostBreakdown(model, [ds]);
    expect(result.hasAnyPricing).toBe(true);
    expect(result.totalCost).toBeGreaterThan(0);
    expect(result.dataSources).toHaveLength(1);
  });
});

// ============================================================================
// formatCurrency
// ============================================================================

describe('formatCurrency', () => {
  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00');
  });

  it('formats very small values in exponential', () => {
    expect(formatCurrency(0.000_01)).toMatch(/^\$.*e/);
  });

  it('formats sub-penny with 6 decimals', () => {
    const result = formatCurrency(0.005);
    expect(result).toMatch(/^\$0\.005/);
  });

  it('formats sub-dollar with 4 decimals', () => {
    const result = formatCurrency(0.5);
    expect(result).toBe('$0.5000');
  });

  it('formats dollar amounts with Intl formatter', () => {
    const result = formatCurrency(1234.56);
    expect(result).toContain('1,234.56');
  });
});

// ============================================================================
// formatCostPerUnit
// ============================================================================

describe('formatCostPerUnit', () => {
  it('returns dash for zero value', () => {
    expect(formatCostPerUnit(0, 'token')).toBe('—');
  });

  it('formats per million tokens', () => {
    const result = formatCostPerUnit(0.000_01, 'token');
    expect(result).toContain('/ 1M');
  });

  it('formats per billion tokens for tiny values', () => {
    const result = formatCostPerUnit(0.000_000_000_01, 'token');
    expect(result).toContain('/ 1B');
  });

  it('formats per query', () => {
    const result = formatCostPerUnit(0.5, 'query');
    expect(result).toContain('/ 1K');
  });

  it('formats per request', () => {
    const result = formatCostPerUnit(0.05, 'request');
    expect(result).toContain('/ request');
  });

  it('formats per call', () => {
    const result = formatCostPerUnit(0.05, 'call');
    expect(result).toContain('/ call');
  });

  it('returns dash for zero call value', () => {
    expect(formatCostPerUnit(0, 'call')).toBe('—');
  });

  it('formats tiny per-call values in exponential', () => {
    const result = formatCostPerUnit(0.000_000_5, 'call');
    expect(result).toContain('/ call');
    expect(result).toContain('e');
  });
});

// ============================================================================
// formatTokenCount
// ============================================================================

describe('formatTokenCount', () => {
  it('formats numbers below 1000 as-is', () => {
    expect(formatTokenCount(500)).toBe('500');
  });

  it('formats thousands with K suffix', () => {
    expect(formatTokenCount(1500)).toBe('1.5K');
  });

  it('formats millions with M suffix', () => {
    expect(formatTokenCount(2_500_000)).toBe('2.5M');
  });
});

// ============================================================================
// getCostPercentage
// ============================================================================

describe('getCostPercentage', () => {
  it('returns 0 for zero total', () => {
    expect(getCostPercentage(50, 0)).toBe(0);
  });

  it('calculates correct percentage', () => {
    expect(getCostPercentage(25, 100)).toBe(25);
  });

  it('caps at 100', () => {
    expect(getCostPercentage(200, 100)).toBe(100);
  });
});

// ============================================================================
// estimatePerRequestCost
// ============================================================================

describe('estimatePerRequestCost', () => {
  it('returns null for null source', () => {
    expect(estimatePerRequestCost(null)).toBeNull();
  });

  it('returns null for source without pricing', () => {
    const source = createMockChatSource({ policies: [] });
    expect(estimatePerRequestCost(source)).toBeNull();
  });

  it('calculates per-token estimate', () => {
    const source = createMockChatSource({
      policies: [
        {
          type: 'transaction',
          version: '1.0',
          enabled: true,
          description: '',
          config: { costs: { inputTokens: 0.001, outputTokens: 0.002, currency: 'USD' } }
        }
      ]
    });
    // Default params: 500 input, 1000 output
    const result = estimatePerRequestCost(source);
    expect(result).toBeCloseTo(0.5 + 2); // 500*0.001 + 1000*0.002
  });

  it('returns flat pricePerCall for per-call pricing', () => {
    const source = createMockChatSource({
      policies: [
        {
          type: 'accounting',
          version: '1.0',
          enabled: true,
          description: '',
          config: { pricingMode: 'per_call', price: 0.05 }
        }
      ]
    });
    expect(estimatePerRequestCost(source)).toBe(0.05);
  });

  it('returns null for per-call pricing with zero price', () => {
    const source = createMockChatSource({
      policies: [
        {
          type: 'accounting',
          version: '1.0',
          enabled: true,
          description: '',
          config: { pricingMode: 'per_call', price: 0 }
        }
      ]
    });
    expect(estimatePerRequestCost(source)).toBeNull();
  });
});

// ============================================================================
// formatPerRequestCost
// ============================================================================

describe('formatPerRequestCost', () => {
  it('returns null for null cost', () => {
    expect(formatPerRequestCost(null)).toBeNull();
  });

  it('returns null for zero cost', () => {
    expect(formatPerRequestCost(0)).toBeNull();
  });

  it('formats small cost with 4 decimals', () => {
    const result = formatPerRequestCost(0.005);
    expect(result).toBe('~$0.0050/req');
  });

  it('formats sub-dollar cost with 3 decimals', () => {
    const result = formatPerRequestCost(0.05);
    expect(result).toBe('~$0.050/req');
  });

  it('formats dollar+ cost with 2 decimals', () => {
    const result = formatPerRequestCost(1.5);
    expect(result).toBe('~$1.50/req');
  });

  it('formats very tiny cost in exponential', () => {
    const result = formatPerRequestCost(0.000_000_5);
    expect(result).toContain('~');
    expect(result).toContain('/req');
    expect(result).toContain('e');
  });
});
