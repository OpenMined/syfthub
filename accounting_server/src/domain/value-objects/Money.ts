/**
 * Money Value Object
 *
 * Immutable representation of monetary values.
 * Uses bigint for precision to avoid floating-point issues.
 */

export type Currency = 'CREDIT' | 'USD' | 'EUR' | 'GBP';

export class Money {
  private constructor(
    public readonly amount: bigint,
    public readonly currency: Currency
  ) {
    if (amount < 0n) {
      throw new Error('Money amount cannot be negative');
    }
  }

  /**
   * Create Money from a bigint amount (smallest unit)
   */
  static fromSmallestUnit(amount: bigint, currency: Currency): Money {
    return new Money(amount, currency);
  }

  /**
   * Create Money from a string amount (smallest unit)
   */
  static fromString(amount: string, currency: Currency): Money {
    const parsed = BigInt(amount);
    return new Money(parsed, currency);
  }

  /**
   * Create zero Money
   */
  static zero(currency: Currency): Money {
    return new Money(0n, currency);
  }

  /**
   * Create Money in CREDIT currency
   */
  static credits(amount: bigint): Money {
    return new Money(amount, 'CREDIT');
  }

  /**
   * Add two Money values (must be same currency)
   */
  add(other: Money): Money {
    this.assertSameCurrency(other);
    return new Money(this.amount + other.amount, this.currency);
  }

  /**
   * Subtract Money value (must be same currency)
   */
  subtract(other: Money): Money {
    this.assertSameCurrency(other);
    if (this.amount < other.amount) {
      throw new Error('Subtraction would result in negative amount');
    }
    return new Money(this.amount - other.amount, this.currency);
  }

  /**
   * Multiply by a factor (for fee calculations, etc.)
   */
  multiply(factor: number): Money {
    const result = BigInt(Math.floor(Number(this.amount) * factor));
    return new Money(result, this.currency);
  }

  /**
   * Check if this Money is greater than another
   */
  isGreaterThan(other: Money): boolean {
    this.assertSameCurrency(other);
    return this.amount > other.amount;
  }

  /**
   * Check if this Money is greater than or equal to another
   */
  isGreaterThanOrEqual(other: Money): boolean {
    this.assertSameCurrency(other);
    return this.amount >= other.amount;
  }

  /**
   * Check if this Money is less than another
   */
  isLessThan(other: Money): boolean {
    this.assertSameCurrency(other);
    return this.amount < other.amount;
  }

  /**
   * Check if this Money is zero
   */
  isZero(): boolean {
    return this.amount === 0n;
  }

  /**
   * Check if this Money is positive
   */
  isPositive(): boolean {
    return this.amount > 0n;
  }

  /**
   * Check equality
   */
  equals(other: Money): boolean {
    return this.amount === other.amount && this.currency === other.currency;
  }

  /**
   * Convert to JSON-serializable object
   */
  toJSON(): { amount: string; currency: Currency } {
    return {
      amount: this.amount.toString(),
      currency: this.currency,
    };
  }

  /**
   * String representation
   */
  toString(): string {
    return `${this.amount} ${this.currency}`;
  }

  private assertSameCurrency(other: Money): void {
    if (this.currency !== other.currency) {
      throw new Error(
        `Currency mismatch: ${this.currency} vs ${other.currency}`
      );
    }
  }
}
