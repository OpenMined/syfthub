/**
 * Payment Provider Factory
 *
 * Creates and manages payment provider adapter instances.
 * Implements the Factory pattern for extensible provider integration.
 */

import { PaymentProviderGateway } from '../../application/ports/output/PaymentProviderGateway';
import { ProviderCode } from '../../domain/entities/Transaction';
import { StripeAdapter } from './StripeAdapter';
import { PixAdapter, PixPspConfig } from './pix';
import { XenditAdapter, XenditConfig } from './xendit';

export interface ProviderConfig {
  stripe?: {
    enabled: boolean;
    apiKey: string;
    webhookSecret: string;
  } | undefined;
  paypal?: {
    enabled: boolean;
    clientId: string;
    clientSecret: string;
    webhookId: string;
    sandbox: boolean;
  } | undefined;
  bankTransfer?: {
    enabled: boolean;
    // Bank-specific configuration
  } | undefined;
  pix?: {
    enabled: boolean;
    config: PixPspConfig;
  } | undefined;
  xendit?: {
    enabled: boolean;
    config: XenditConfig;
  } | undefined;
}

export class UnsupportedProviderError extends Error {
  constructor(providerCode: string) {
    super(`Payment provider '${providerCode}' is not configured or supported`);
    this.name = 'UnsupportedProviderError';
  }
}

export class PaymentProviderFactory {
  private providers: Map<ProviderCode, PaymentProviderGateway> = new Map();

  constructor(config: ProviderConfig) {
    this.initializeProviders(config);
  }

  /**
   * Get a provider by code
   * @throws UnsupportedProviderError if provider is not configured
   */
  getProvider(code: ProviderCode): PaymentProviderGateway {
    const provider = this.providers.get(code);

    if (!provider) {
      throw new UnsupportedProviderError(code);
    }

    return provider;
  }

  /**
   * Check if a provider is available
   */
  hasProvider(code: ProviderCode): boolean {
    return this.providers.has(code);
  }

  /**
   * Get list of all configured provider codes
   */
  getSupportedProviders(): ProviderCode[] {
    return Array.from(this.providers.keys());
  }

  /**
   * Get provider by webhook path
   * Maps webhook URL paths to provider codes
   */
  getProviderByWebhookPath(path: string): PaymentProviderGateway | null {
    const pathToProvider: Record<string, ProviderCode> = {
      stripe: 'stripe',
      paypal: 'paypal',
      'bank-transfer': 'bank_transfer',
      pix: 'pix',
      xendit: 'xendit',
    };

    const providerCode = pathToProvider[path];
    if (!providerCode) {
      return null;
    }

    if (!this.hasProvider(providerCode)) {
      return null;
    }

    return this.getProvider(providerCode);
  }

  /**
   * Get provider for a specific operation type
   * Can implement logic to route to different providers based on criteria
   */
  getProviderForDeposit(
    amount: bigint,
    currency: string,
    preferredProvider?: ProviderCode
  ): PaymentProviderGateway {
    // If preferred provider is specified and available, use it
    if (preferredProvider && this.hasProvider(preferredProvider)) {
      return this.getProvider(preferredProvider);
    }

    // Default routing logic - can be customized
    // For now, prefer Stripe for card payments
    if (this.hasProvider('stripe')) {
      return this.getProvider('stripe');
    }

    // Fallback to any available provider
    const available = this.getSupportedProviders();
    const firstProvider = available[0];
    if (firstProvider) {
      return this.getProvider(firstProvider);
    }

    throw new UnsupportedProviderError('No payment providers configured');
  }

  /**
   * Get provider for withdrawal operations
   * May have different routing logic than deposits
   */
  getProviderForWithdrawal(
    destinationType: 'bank_account' | 'card' | 'wallet',
    preferredProvider?: ProviderCode
  ): PaymentProviderGateway {
    if (preferredProvider && this.hasProvider(preferredProvider)) {
      return this.getProvider(preferredProvider);
    }

    // Route based on destination type
    if (destinationType === 'bank_account') {
      // Prefer bank transfer provider for bank accounts
      if (this.hasProvider('bank_transfer')) {
        return this.getProvider('bank_transfer');
      }
    }

    // Default to Stripe for card payouts
    if (this.hasProvider('stripe')) {
      return this.getProvider('stripe');
    }

    throw new UnsupportedProviderError(
      `No provider available for ${destinationType} withdrawals`
    );
  }

  private initializeProviders(config: ProviderConfig): void {
    // Initialize Stripe
    if (config.stripe?.enabled) {
      this.providers.set(
        'stripe',
        new StripeAdapter({
          apiKey: config.stripe.apiKey,
          webhookSecret: config.stripe.webhookSecret,
        })
      );
    }

    // Initialize PayPal (placeholder - implementation similar to Stripe)
    if (config.paypal?.enabled) {
      // this.providers.set('paypal', new PayPalAdapter({
      //   clientId: config.paypal.clientId,
      //   clientSecret: config.paypal.clientSecret,
      //   webhookId: config.paypal.webhookId,
      //   sandbox: config.paypal.sandbox,
      // }));
      console.warn('PayPal adapter not yet implemented');
    }

    // Initialize Bank Transfer (placeholder)
    if (config.bankTransfer?.enabled) {
      // this.providers.set('bank_transfer', new BankTransferAdapter(config.bankTransfer));
      console.warn('Bank Transfer adapter not yet implemented');
    }

    // Initialize PIX (Brazilian Instant Payment)
    if (config.pix?.enabled) {
      this.providers.set('pix', new PixAdapter(config.pix.config));
    }

    // Initialize Xendit (Southeast Asia)
    if (config.xendit?.enabled) {
      this.providers.set('xendit', new XenditAdapter(config.xendit.config));
    }
  }

  /**
   * Get the PIX adapter with PIX-specific methods
   * @throws UnsupportedProviderError if PIX is not configured
   */
  getPixAdapter(): PixAdapter {
    const provider = this.providers.get('pix');
    if (!provider) {
      throw new UnsupportedProviderError('pix');
    }
    return provider as PixAdapter;
  }

  /**
   * Get the Xendit adapter with Xendit-specific methods
   * @throws UnsupportedProviderError if Xendit is not configured
   */
  getXenditAdapter(): XenditAdapter {
    const provider = this.providers.get('xendit');
    if (!provider) {
      throw new UnsupportedProviderError('xendit');
    }
    return provider as XenditAdapter;
  }
}
