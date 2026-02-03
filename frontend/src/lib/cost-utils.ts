/**
 * Cost calculation utilities for transaction policies
 * Extracts pricing information from endpoint policies and calculates estimated costs
 */

import type { ChatSource, Policy } from './types';

// ============================================================================
// Types
// ============================================================================

export type PricingMode = 'per_token' | 'per_call';

export interface TransactionCosts {
  inputPerToken: number;
  outputPerToken: number;
  currency: string;
  pricingMode: PricingMode;
  pricePerCall: number;
}

export interface CostEstimate {
  inputCost: number;
  outputCost: number;
  totalCost: number;
}

export interface ModelCostBreakdown {
  name: string;
  slug: string;
  inputCost: number;
  outputCost: number;
  totalCost: number;
  hasPolicy: boolean;
  pricingMode: PricingMode;
}

// Data sources also use token-based pricing (same structure as models)
export interface DataSourceCostBreakdown {
  name: string;
  slug: string;
  inputCost: number;
  outputCost: number;
  totalCost: number;
  hasPolicy: boolean;
  pricingMode: PricingMode;
}

export interface FullCostBreakdown {
  model: ModelCostBreakdown | null;
  dataSources: DataSourceCostBreakdown[];
  totalModelCost: number;
  totalDataSourceCost: number;
  totalInputCost: number;
  totalOutputCost: number;
  totalPerCallCost: number;
  totalCost: number;
  hasAnyPricing: boolean;
}

export interface EstimationParams {
  estimatedInputTokens: number;
  estimatedOutputTokens: number;
  queriesPerSource: number;
}

// Default estimation parameters
export const DEFAULT_ESTIMATION_PARAMS: EstimationParams = {
  estimatedInputTokens: 500,
  estimatedOutputTokens: 1000,
  queriesPerSource: 1
};

// ============================================================================
// Policy Extraction
// ============================================================================

/**
 * Extracts transaction policy from an array of policies
 */
export function extractTransactionPolicy(policies?: Policy[]): Policy | null {
  if (!policies || policies.length === 0) return null;

  return policies.find((p) => p.type.toLowerCase() === 'transaction' && p.enabled) ?? null;
}

/**
 * Extracts cost information from a transaction policy config
 */
export function extractCostsFromPolicy(policy: Policy | null): TransactionCosts {
  const defaultCosts: TransactionCosts = {
    inputPerToken: 0,
    outputPerToken: 0,
    currency: 'USD',
    pricingMode: 'per_token',
    pricePerCall: 0
  };

  if (!policy?.config) return defaultCosts;

  const config = policy.config;

  // Detect per-call pricing (config.pricingMode is camelCase-transformed from pricing_mode)
  if (config.pricingMode === 'per_call' && typeof config.price === 'number') {
    return {
      inputPerToken: 0,
      outputPerToken: 0,
      currency: typeof config.currency === 'string' ? config.currency : 'USD',
      pricingMode: 'per_call',
      pricePerCall: config.price
    };
  }

  // Per-token pricing path
  const costs = config.costs as Record<string, unknown> | undefined;

  if (!costs) return defaultCosts;

  return {
    // Field names are camelCase due to SDK transformation (input_tokens -> inputTokens)
    inputPerToken: typeof costs.inputTokens === 'number' ? costs.inputTokens : 0,
    outputPerToken: typeof costs.outputTokens === 'number' ? costs.outputTokens : 0,
    currency: typeof costs.currency === 'string' ? costs.currency : 'USD',
    pricingMode: 'per_token',
    pricePerCall: 0
  };
}

/**
 * Gets transaction costs from a ChatSource
 */
export function getCostsFromSource(source: ChatSource | null): TransactionCosts {
  if (!source) {
    return {
      inputPerToken: 0,
      outputPerToken: 0,
      currency: 'USD',
      pricingMode: 'per_token',
      pricePerCall: 0
    };
  }

  const policy = extractTransactionPolicy(source.policies);
  return extractCostsFromPolicy(policy);
}

// ============================================================================
// Cost Calculation
// ============================================================================

/**
 * Calculates model cost based on token estimates
 */
export function calculateModelCost(
  source: ChatSource | null,
  params: EstimationParams
): ModelCostBreakdown | null {
  if (!source) return null;

  const costs = getCostsFromSource(source);

  if (costs.pricingMode === 'per_call') {
    return {
      name: source.name,
      slug: source.slug,
      inputCost: 0,
      outputCost: 0,
      totalCost: costs.pricePerCall,
      hasPolicy: costs.pricePerCall > 0,
      pricingMode: 'per_call'
    };
  }

  const hasPolicy = costs.inputPerToken > 0 || costs.outputPerToken > 0;
  const inputCost = params.estimatedInputTokens * costs.inputPerToken;
  const outputCost = params.estimatedOutputTokens * costs.outputPerToken;

  return {
    name: source.name,
    slug: source.slug,
    inputCost,
    outputCost,
    totalCost: inputCost + outputCost,
    hasPolicy,
    pricingMode: 'per_token'
  };
}

/**
 * Calculates data source cost (token-based, same as models)
 */
export function calculateDataSourceCost(
  source: ChatSource,
  params: EstimationParams
): DataSourceCostBreakdown {
  const costs = getCostsFromSource(source);

  if (costs.pricingMode === 'per_call') {
    return {
      name: source.name,
      slug: source.slug,
      inputCost: 0,
      outputCost: 0,
      totalCost: costs.pricePerCall,
      hasPolicy: costs.pricePerCall > 0,
      pricingMode: 'per_call'
    };
  }

  const hasPolicy = costs.inputPerToken > 0 || costs.outputPerToken > 0;

  // Data sources use token-based pricing for RAG queries
  const inputCost = params.estimatedInputTokens * costs.inputPerToken;
  const outputCost = params.estimatedOutputTokens * costs.outputPerToken;

  return {
    name: source.name,
    slug: source.slug,
    inputCost,
    outputCost,
    totalCost: inputCost + outputCost,
    hasPolicy,
    pricingMode: 'per_token'
  };
}

/**
 * Calculates full cost breakdown for a chat query
 */
export function calculateFullCostBreakdown(
  model: ChatSource | null,
  dataSources: ChatSource[],
  params: EstimationParams = DEFAULT_ESTIMATION_PARAMS
): FullCostBreakdown {
  const modelBreakdown = calculateModelCost(model, params);
  const dataSourceBreakdowns = dataSources.map((ds) => calculateDataSourceCost(ds, params));

  const totalModelCost = modelBreakdown?.totalCost ?? 0;
  const totalDataSourceCost = dataSourceBreakdowns.reduce((sum, ds) => sum + ds.totalCost, 0);

  // Separate per-call costs from per-token input/output costs
  const allBreakdowns = [...(modelBreakdown ? [modelBreakdown] : []), ...dataSourceBreakdowns];

  const totalInputCost = allBreakdowns
    .filter((b) => b.pricingMode === 'per_token')
    .reduce((sum, b) => sum + b.inputCost, 0);

  const totalOutputCost = allBreakdowns
    .filter((b) => b.pricingMode === 'per_token')
    .reduce((sum, b) => sum + b.outputCost, 0);

  const totalPerCallCost = allBreakdowns
    .filter((b) => b.pricingMode === 'per_call')
    .reduce((sum, b) => sum + b.totalCost, 0);

  const hasAnyPricing =
    (modelBreakdown?.hasPolicy ?? false) || dataSourceBreakdowns.some((ds) => ds.hasPolicy);

  return {
    model: modelBreakdown,
    dataSources: dataSourceBreakdowns,
    totalModelCost,
    totalDataSourceCost,
    totalInputCost,
    totalOutputCost,
    totalPerCallCost,
    totalCost: totalInputCost + totalOutputCost + totalPerCallCost,
    hasAnyPricing
  };
}

// ============================================================================
// Formatting
// ============================================================================

/**
 * Formats a cost value as currency
 */
export function formatCurrency(value: number, currency = 'USD'): string {
  if (value === 0) return '$0.00';

  // For very small values, show more precision
  if (value < 0.0001) {
    return `$${value.toExponential(2)}`;
  }

  if (value < 0.01) {
    return `$${value.toFixed(6)}`;
  }

  if (value < 1) {
    return `$${value.toFixed(4)}`;
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4
  }).format(value);
}

/**
 * Formats cost per unit (e.g., per million tokens, per request)
 */
export function formatCostPerUnit(
  value: number,
  unit: 'token' | 'query' | 'request' | 'call'
): string {
  if (value === 0) return '—';

  if (unit === 'token') {
    const perMillion = value * 1_000_000;
    if (perMillion < 0.01) {
      return `$${(perMillion * 1000).toFixed(2)} / 1B`;
    }
    return `$${perMillion.toFixed(2)} / 1M`;
  }

  if (unit === 'call') {
    // Per call - flat price per API call
    if (value < 0.000_001) {
      return `$${value.toExponential(2)} / call`;
    }
    if (value < 0.01) {
      return `$${value.toFixed(6)} / call`;
    }
    return `$${value.toFixed(4)} / call`;
  }

  if (unit === 'request') {
    // Per request - show cost for each individual request
    if (value < 0.000_001) {
      return `$${value.toExponential(2)} / request`;
    }
    if (value < 0.01) {
      return `$${value.toFixed(6)} / request`;
    }
    return `$${value.toFixed(4)} / request`;
  }

  // Per query
  const perThousand = value * 1000;
  if (perThousand < 0.01) {
    return `$${value.toFixed(6)} / query`;
  }
  return `$${perThousand.toFixed(2)} / 1K`;
}

/**
 * Formats token count with K/M suffix
 */
export function formatTokenCount(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  return count.toString();
}

/**
 * Estimates the cost per request for a model using default token estimates.
 * Returns null if the model has no pricing policy.
 */
export function estimatePerRequestCost(
  source: ChatSource | null,
  params: EstimationParams = DEFAULT_ESTIMATION_PARAMS
): number | null {
  if (!source) return null;

  const costs = getCostsFromSource(source);

  if (costs.pricingMode === 'per_call') {
    return costs.pricePerCall > 0 ? costs.pricePerCall : null;
  }

  const hasPolicy = costs.inputPerToken > 0 || costs.outputPerToken > 0;
  if (!hasPolicy) return null;

  return (
    params.estimatedInputTokens * costs.inputPerToken +
    params.estimatedOutputTokens * costs.outputPerToken
  );
}

/**
 * Formats an estimated per-request cost for compact display (e.g., "~$0.003/req")
 */
export function formatPerRequestCost(cost: number | null): string | null {
  if (cost === null || cost === 0) return null;

  if (cost < 0.000_001) {
    return `~${cost.toExponential(1)}/req`;
  }
  if (cost < 0.01) {
    return `~$${cost.toFixed(4)}/req`;
  }
  if (cost < 1) {
    return `~$${cost.toFixed(3)}/req`;
  }
  return `~$${cost.toFixed(2)}/req`;
}

/**
 * Gets a percentage for visual representation
 */
export function getCostPercentage(cost: number, total: number): number {
  if (total === 0) return 0;
  return Math.min((cost / total) * 100, 100);
}
