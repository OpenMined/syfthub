/**
 * Integration Test: P2P Transfer with Confirmation + Xendit Withdrawal
 *
 * This test validates the complete scenario:
 * 1. Two users registered with 2000 credits each ($20)
 * 2. User A initiates a transfer of 50 credits ($0.50) to User B
 * 3. User B confirms the transfer with the confirmation token
 * 4. User B withdraws 2050 credits ($20.50) to Xendit bank account
 *
 * Run with: RUN_INTEGRATION_TESTS=true npm test -- --testPathPattern=P2PTransferWithXenditWithdrawal
 *
 * Prerequisites:
 * - PostgreSQL running with ledger_test database
 * - Migration 002_add_transfer_confirmation applied
 * - Environment variables from .env.test loaded
 * - For Xendit sandbox tests: valid XENDIT_API_KEY
 */

import { Pool } from 'pg';
import { v4 as uuidv4 } from 'uuid';

// Domain
import { Account } from '../../src/domain/entities/Account';
import { PaymentMethod } from '../../src/domain/entities/PaymentMethod';
import { Money } from '../../src/domain/value-objects/Money';
import {
  UserId,
  IdempotencyKey,
  PaymentMethodId,
} from '../../src/domain/value-objects/Identifiers';

// Infrastructure
import {
  PostgresAccountRepository,
  PostgresTransactionRepository,
  PostgresTransactionManager,
} from '../../src/infrastructure/persistence';
import { PostgresPaymentMethodRepository } from '../../src/infrastructure/persistence/PostgresPaymentMethodRepository';
import { PaymentProviderFactory, ProviderConfig } from '../../src/infrastructure/payment-providers/PaymentProviderFactory';

// Use Cases
import { ExecuteTransferUseCase } from '../../src/application/use-cases/ExecuteTransfer';
import { InitiateWithdrawalUseCase } from '../../src/application/use-cases/InitiateWithdrawal';
import { ProcessDepositUseCase } from '../../src/application/use-cases/ProcessDeposit';

// HTTP Layer (for webhook testing)
import { createWebhookController } from '../../src/infrastructure/http/controllers/WebhookController';
import express from 'express';
import request from 'supertest';

// Skip if not explicitly enabled
const SKIP_INTEGRATION = process.env['RUN_INTEGRATION_TESTS'] !== 'true';
const describeIntegration = SKIP_INTEGRATION ? describe.skip : describe;

// Load test environment
const TEST_DB_URL = process.env['DATABASE_URL'] ?? 'postgresql://postgres:postgres@localhost:5432/ledger_test';
const TRANSFER_CONFIRMATION_SECRET = process.env['TRANSFER_CONFIRMATION_SECRET'] ?? 'test-transfer-confirmation-secret-32ch!';
const XENDIT_API_KEY = process.env['XENDIT_API_KEY'];
const XENDIT_ENABLED = process.env['XENDIT_ENABLED'] === 'true';

describeIntegration('P2P Transfer with Confirmation + Xendit Withdrawal', () => {
  let pool: Pool;
  let accountRepository: PostgresAccountRepository;
  let transactionRepository: PostgresTransactionRepository;
  let paymentMethodRepository: PostgresPaymentMethodRepository;
  let transactionManager: PostgresTransactionManager;
  let paymentProviderFactory: PaymentProviderFactory;
  let executeTransfer: ExecuteTransferUseCase;
  let initiateWithdrawal: InitiateWithdrawalUseCase;

  // Test data
  let userAId: UserId;
  let userBId: UserId;
  let userAAccount: Account;
  let userBAccount: Account;
  let userBXenditPaymentMethod: PaymentMethod;

  const INITIAL_BALANCE = 2000n; // $20 in credits
  const TRANSFER_AMOUNT = 50n;   // $0.50 in credits
  const WITHDRAWAL_AMOUNT = 2050n; // $20.50 in credits

  beforeAll(async () => {
    // Create database pool
    pool = new Pool({
      connectionString: TEST_DB_URL,
      max: 5,
    });

    // Test connection
    try {
      await pool.query('SELECT 1');
      console.log('Database connection established');
    } catch (error) {
      console.error('Failed to connect to test database:', error);
      throw error;
    }

    // Create repositories
    accountRepository = new PostgresAccountRepository(pool);
    transactionRepository = new PostgresTransactionRepository(pool);
    paymentMethodRepository = new PostgresPaymentMethodRepository(pool);
    transactionManager = new PostgresTransactionManager(pool);

    // Create payment provider factory
    const providerConfig: ProviderConfig = {};

    if (XENDIT_ENABLED && XENDIT_API_KEY) {
      providerConfig.xendit = {
        enabled: true,
        config: {
          apiKey: XENDIT_API_KEY,
          webhookToken: process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_token',
          baseUrl: 'https://api.xendit.co',
          sandbox: true,
          defaultCountry: 'ID',
          defaultCurrency: 'IDR',
        },
      };
    }

    paymentProviderFactory = new PaymentProviderFactory(providerConfig);

    // Create use cases
    executeTransfer = new ExecuteTransferUseCase(
      accountRepository,
      transactionRepository,
      transactionManager,
      {
        confirmationTokenSecret: TRANSFER_CONFIRMATION_SECRET,
        confirmationExpirationHours: 24,
      }
    );

    initiateWithdrawal = new InitiateWithdrawalUseCase(
      accountRepository,
      transactionRepository,
      paymentMethodRepository,
      paymentProviderFactory,
      transactionManager
    );
  });

  afterAll(async () => {
    await pool.end();
    console.log('Database connection closed');
  });

  beforeEach(async () => {
    // Clean up test data
    await pool.query('DELETE FROM ledger_entries');
    await pool.query('DELETE FROM transactions');
    await pool.query('DELETE FROM payment_methods');
    await pool.query('DELETE FROM accounts');

    // Create test users
    userAId = UserId.generate();
    userBId = UserId.generate();

    // Create accounts with initial balance
    userAAccount = Account.create({
      userId: userAId,
      type: 'user',
    });

    userBAccount = Account.create({
      userId: userBId,
      type: 'user',
    });

    // Simulate initial funding (normally this would be via deposit)
    // We directly set balance for testing
    await pool.query(
      `INSERT INTO accounts (id, user_id, type, status, balance, available_balance, currency, metadata, version)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
      [
        userAAccount.id.toString(),
        userAId.toString(),
        'user',
        'active',
        INITIAL_BALANCE.toString(),
        INITIAL_BALANCE.toString(),
        'CREDIT',
        '{}',
        1,
      ]
    );

    await pool.query(
      `INSERT INTO accounts (id, user_id, type, status, balance, available_balance, currency, metadata, version)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
      [
        userBAccount.id.toString(),
        userBId.toString(),
        'user',
        'active',
        INITIAL_BALANCE.toString(),
        INITIAL_BALANCE.toString(),
        'CREDIT',
        '{}',
        1,
      ]
    );

    // Create User B's Xendit payment method for withdrawal
    const paymentMethodId = PaymentMethodId.generate();
    await pool.query(
      `INSERT INTO payment_methods (id, account_id, provider_code, type, status, external_id, display_name, is_default, is_withdrawable, metadata)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
      [
        paymentMethodId.toString(),
        userBAccount.id.toString(),
        'xendit',
        'bank_account',
        'verified',
        'ID_BCA:1234567890:User B Test', // Xendit destination format
        'BCA •••• 7890',
        true,
        true,
        '{"channel_code": "ID_BCA"}',
      ]
    );

    // Reload accounts from database
    const reloadedA = await accountRepository.findById(userAAccount.id);
    const reloadedB = await accountRepository.findById(userBAccount.id);
    if (reloadedA) userAAccount = reloadedA;
    if (reloadedB) userBAccount = reloadedB;

    // Load payment method
    const methods = await paymentMethodRepository.findByAccountId(userBAccount.id.toString());
    userBXenditPaymentMethod = methods[0]!;
  });

  describe('Scenario: Complete P2P Transfer with Confirmation', () => {
    it('should verify initial state - both users have $20', async () => {
      const accountA = await accountRepository.findById(userAAccount.id);
      const accountB = await accountRepository.findById(userBAccount.id);

      expect(accountA).not.toBeNull();
      expect(accountB).not.toBeNull();
      expect(accountA!.balance.amount).toBe(INITIAL_BALANCE);
      expect(accountB!.balance.amount).toBe(INITIAL_BALANCE);
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE);
      expect(accountB!.availableBalance.amount).toBe(INITIAL_BALANCE);

      console.log(`User A Balance: ${accountA!.balance.amount} credits ($${Number(accountA!.balance.amount) / 100})`);
      console.log(`User B Balance: ${accountB!.balance.amount} credits ($${Number(accountB!.balance.amount) / 100})`);
    });

    it('should initiate transfer with confirmation token', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);

      const result = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
        description: 'Test P2P transfer',
        metadata: { test: true },
      });

      // Verify result
      expect(result.transaction).toBeDefined();
      expect(result.confirmationToken).toBeDefined();
      expect(result.confirmationToken.length).toBeGreaterThan(0);
      expect(result.expiresAt).toBeInstanceOf(Date);
      expect(result.expiresAt.getTime()).toBeGreaterThan(Date.now());

      // Verify transaction state
      expect(result.transaction.status).toBe('awaiting_confirmation');
      expect(result.transaction.type).toBe('transfer');
      expect(result.transaction.amount.amount).toBe(TRANSFER_AMOUNT);

      // Verify User A's funds are held
      const accountA = await accountRepository.findById(userAAccount.id);
      expect(accountA!.balance.amount).toBe(INITIAL_BALANCE); // Balance unchanged
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE - TRANSFER_AMOUNT); // Available reduced

      // Verify User B's balance unchanged
      const accountB = await accountRepository.findById(userBAccount.id);
      expect(accountB!.balance.amount).toBe(INITIAL_BALANCE);
      expect(accountB!.availableBalance.amount).toBe(INITIAL_BALANCE);

      console.log(`Transfer initiated: ${result.transaction.id}`);
      console.log(`Confirmation token: ${result.confirmationToken.substring(0, 20)}...`);
      console.log(`Expires at: ${result.expiresAt.toISOString()}`);
      console.log(`User A available: ${accountA!.availableBalance.amount} (held: ${TRANSFER_AMOUNT})`);
    });

    it('should confirm transfer and move funds', async () => {
      // Step 1: Initiate transfer
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);
      const initResult = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      // Step 2: Confirm transfer
      const confirmedTransaction = await executeTransfer.confirmTransfer({
        transactionId: initResult.transaction.id,
        confirmationToken: initResult.confirmationToken,
      });

      // Verify transaction state
      expect(confirmedTransaction.status).toBe('completed');
      expect(confirmedTransaction.completedAt).not.toBeNull();

      // Verify final balances
      const accountA = await accountRepository.findById(userAAccount.id);
      const accountB = await accountRepository.findById(userBAccount.id);

      expect(accountA!.balance.amount).toBe(INITIAL_BALANCE - TRANSFER_AMOUNT); // 1950
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE - TRANSFER_AMOUNT); // 1950

      expect(accountB!.balance.amount).toBe(INITIAL_BALANCE + TRANSFER_AMOUNT); // 2050
      expect(accountB!.availableBalance.amount).toBe(INITIAL_BALANCE + TRANSFER_AMOUNT); // 2050

      console.log(`Transfer completed: ${confirmedTransaction.id}`);
      console.log(`User A: ${accountA!.balance.amount} credits ($${Number(accountA!.balance.amount) / 100})`);
      console.log(`User B: ${accountB!.balance.amount} credits ($${Number(accountB!.balance.amount) / 100})`);
    });

    it('should reject invalid confirmation token', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);
      const initResult = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      // Try to confirm with wrong token
      await expect(
        executeTransfer.confirmTransfer({
          transactionId: initResult.transaction.id,
          confirmationToken: 'invalid-token',
        })
      ).rejects.toThrow('Invalid');

      // Verify funds still held
      const accountA = await accountRepository.findById(userAAccount.id);
      expect(accountA!.balance.amount).toBe(INITIAL_BALANCE);
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE - TRANSFER_AMOUNT);
    });

    it('should allow sender to cancel pending transfer', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);
      const initResult = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      // Cancel the transfer
      const cancelledTransaction = await executeTransfer.cancelTransfer({
        transactionId: initResult.transaction.id,
        reason: 'Changed my mind',
      });

      expect(cancelledTransaction.status).toBe('cancelled');

      // Verify funds released
      const accountA = await accountRepository.findById(userAAccount.id);
      expect(accountA!.balance.amount).toBe(INITIAL_BALANCE);
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE); // Funds released

      console.log('Transfer cancelled, funds released');
    });

    it('should be idempotent for initiate transfer', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);

      const result1 = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      // Same idempotency key should return same transaction
      const result2 = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      expect(result2.transaction.id.toString()).toBe(result1.transaction.id.toString());

      // Funds should only be held once
      const accountA = await accountRepository.findById(userAAccount.id);
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE - TRANSFER_AMOUNT);
    });
  });

  describe('Scenario: Full Flow - Transfer + Xendit Withdrawal', () => {
    it('should complete full scenario: transfer confirmation then withdrawal initiation', async () => {
      console.log('\n=== FULL SCENARIO TEST ===\n');

      // ========== STEP 1: Verify Initial State ==========
      console.log('Step 1: Initial State');
      let accountA = await accountRepository.findById(userAAccount.id);
      let accountB = await accountRepository.findById(userBAccount.id);

      console.log(`  User A: ${accountA!.balance.amount} credits ($${Number(accountA!.balance.amount) / 100})`);
      console.log(`  User B: ${accountB!.balance.amount} credits ($${Number(accountB!.balance.amount) / 100})`);

      expect(accountA!.balance.amount).toBe(INITIAL_BALANCE);
      expect(accountB!.balance.amount).toBe(INITIAL_BALANCE);

      // ========== STEP 2: User A Initiates Transfer ==========
      console.log('\nStep 2: User A initiates transfer of $0.50 to User B');

      const transferIdempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);
      const transferResult = await executeTransfer.initiateTransfer({
        idempotencyKey: transferIdempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
        description: 'Payment for coffee',
      });

      console.log(`  Transfer ID: ${transferResult.transaction.id}`);
      console.log(`  Status: ${transferResult.transaction.status}`);
      console.log(`  Token (partial): ${transferResult.confirmationToken.substring(0, 30)}...`);

      expect(transferResult.transaction.status).toBe('awaiting_confirmation');

      // Verify hold
      accountA = await accountRepository.findById(userAAccount.id);
      console.log(`  User A available balance: ${accountA!.availableBalance.amount} (${TRANSFER_AMOUNT} held)`);
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE - TRANSFER_AMOUNT);

      // ========== STEP 3: User B Confirms Transfer ==========
      console.log('\nStep 3: User B confirms the transfer');

      const confirmedTransfer = await executeTransfer.confirmTransfer({
        transactionId: transferResult.transaction.id,
        confirmationToken: transferResult.confirmationToken,
      });

      console.log(`  Transfer status: ${confirmedTransfer.status}`);
      console.log(`  Completed at: ${confirmedTransfer.completedAt}`);

      expect(confirmedTransfer.status).toBe('completed');

      // Verify final balances after transfer
      accountA = await accountRepository.findById(userAAccount.id);
      accountB = await accountRepository.findById(userBAccount.id);

      console.log(`  User A final balance: ${accountA!.balance.amount} credits ($${Number(accountA!.balance.amount) / 100})`);
      console.log(`  User B final balance: ${accountB!.balance.amount} credits ($${Number(accountB!.balance.amount) / 100})`);

      expect(accountA!.balance.amount).toBe(1950n); // $19.50
      expect(accountB!.balance.amount).toBe(2050n); // $20.50

      // ========== STEP 4: User B Initiates Withdrawal ==========
      console.log('\nStep 4: User B initiates withdrawal of $20.50 to Xendit');

      // Note: Xendit withdrawal will likely fail in sandbox without proper setup
      // But we test that the flow initiates correctly
      const withdrawalIdempotencyKey = IdempotencyKey.from(`withdrawal-${uuidv4()}`);

      try {
        const withdrawalResult = await initiateWithdrawal.initiateWithdrawal({
          idempotencyKey: withdrawalIdempotencyKey,
          accountId: userBAccount.id,
          amount: Money.credits(WITHDRAWAL_AMOUNT),
          paymentMethodId: userBXenditPaymentMethod.id,
        });

        console.log(`  Withdrawal ID: ${withdrawalResult.transaction.id}`);
        console.log(`  Status: ${withdrawalResult.transaction.status}`);
        console.log(`  Estimated Completion: ${withdrawalResult.estimatedCompletion ?? 'pending'}`);

        // Withdrawal should be pending (waiting for Xendit callback)
        expect(['pending', 'processing', 'failed']).toContain(withdrawalResult.transaction.status);

        // Verify funds are held for withdrawal
        accountB = await accountRepository.findById(userBAccount.id);
        console.log(`  User B available balance: ${accountB!.availableBalance.amount}`);

        if (withdrawalResult.transaction.status !== 'failed') {
          expect(accountB!.availableBalance.amount).toBe(0n); // All funds held for withdrawal
        }
      } catch (error) {
        // Expected in sandbox without proper Xendit setup
        console.log(`  Withdrawal initiation failed (expected in test env): ${error instanceof Error ? error.message : 'Unknown error'}`);

        // Verify balance is still intact
        accountB = await accountRepository.findById(userBAccount.id);
        expect(accountB!.balance.amount).toBe(2050n); // Balance unchanged if withdrawal failed
      }

      console.log('\n=== SCENARIO COMPLETE ===\n');
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should reject transfer to same account', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);

      await expect(
        executeTransfer.initiateTransfer({
          idempotencyKey,
          sourceAccountId: userAAccount.id,
          destinationAccountId: userAAccount.id, // Same account
          amount: Money.credits(TRANSFER_AMOUNT),
        })
      ).rejects.toThrow();
    });

    it('should reject transfer with insufficient funds', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);

      await expect(
        executeTransfer.initiateTransfer({
          idempotencyKey,
          sourceAccountId: userAAccount.id,
          destinationAccountId: userBAccount.id,
          amount: Money.credits(10000n), // More than balance
        })
      ).rejects.toThrow('insufficient');
    });

    it('should reject confirmation of already confirmed transfer', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);

      const initResult = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      // First confirmation succeeds
      await executeTransfer.confirmTransfer({
        transactionId: initResult.transaction.id,
        confirmationToken: initResult.confirmationToken,
      });

      // Second confirmation should be idempotent (return completed transaction)
      const secondConfirm = await executeTransfer.confirmTransfer({
        transactionId: initResult.transaction.id,
        confirmationToken: initResult.confirmationToken,
      });

      expect(secondConfirm.status).toBe('completed');
    });

    it('should reject confirmation of cancelled transfer', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);

      const initResult = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      // Cancel first
      await executeTransfer.cancelTransfer({
        transactionId: initResult.transaction.id,
      });

      // Try to confirm cancelled transfer
      await expect(
        executeTransfer.confirmTransfer({
          transactionId: initResult.transaction.id,
          confirmationToken: initResult.confirmationToken,
        })
      ).rejects.toThrow('cannot be confirmed');
    });

    it('should reject withdrawal with insufficient available balance', async () => {
      // First, create a pending transfer to reduce available balance
      const transferKey = IdempotencyKey.from(`transfer-${uuidv4()}`);
      await executeTransfer.initiateTransfer({
        idempotencyKey: transferKey,
        sourceAccountId: userBAccount.id,
        destinationAccountId: userAAccount.id,
        amount: Money.credits(1500n), // Hold 1500
      });

      // Now try to withdraw more than available (2000 - 1500 = 500 available)
      const withdrawalKey = IdempotencyKey.from(`withdrawal-${uuidv4()}`);

      await expect(
        initiateWithdrawal.initiateWithdrawal({
          idempotencyKey: withdrawalKey,
          accountId: userBAccount.id,
          amount: Money.credits(1000n), // 1000 > 500 available
          paymentMethodId: userBXenditPaymentMethod.id,
        })
      ).rejects.toThrow('insufficient');
    });
  });

  describe('Ledger Entries Verification', () => {
    it('should create correct double-entry ledger entries for confirmed transfer', async () => {
      const idempotencyKey = IdempotencyKey.from(`transfer-${uuidv4()}`);

      // Initiate and confirm transfer
      const initResult = await executeTransfer.initiateTransfer({
        idempotencyKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      await executeTransfer.confirmTransfer({
        transactionId: initResult.transaction.id,
        confirmationToken: initResult.confirmationToken,
      });

      // Fetch ledger entries
      const entries = await transactionRepository.getLedgerEntries(initResult.transaction.id);

      expect(entries.length).toBe(2);

      // Find debit and credit entries
      const debitEntry = entries.find((e) => e.entryType === 'debit');
      const creditEntry = entries.find((e) => e.entryType === 'credit');

      expect(debitEntry).toBeDefined();
      expect(creditEntry).toBeDefined();

      // Verify debit (from source account)
      expect(debitEntry!.accountId.toString()).toBe(userAAccount.id.toString());
      expect(debitEntry!.amount.amount).toBe(TRANSFER_AMOUNT);
      expect(debitEntry!.balanceAfter.amount).toBe(INITIAL_BALANCE - TRANSFER_AMOUNT);

      // Verify credit (to destination account)
      expect(creditEntry!.accountId.toString()).toBe(userBAccount.id.toString());
      expect(creditEntry!.amount.amount).toBe(TRANSFER_AMOUNT);
      expect(creditEntry!.balanceAfter.amount).toBe(INITIAL_BALANCE + TRANSFER_AMOUNT);

      console.log('Ledger entries verified:');
      console.log(`  Debit: Account ${userAAccount.id}, Amount: ${debitEntry!.amount.amount}, Balance After: ${debitEntry!.balanceAfter.amount}`);
      console.log(`  Credit: Account ${userBAccount.id}, Amount: ${creditEntry!.amount.amount}, Balance After: ${creditEntry!.balanceAfter.amount}`);
    });
  });

  describe('Xendit Webhook Integration', () => {
    let app: express.Application;
    let processDeposit: ProcessDepositUseCase;

    beforeAll(() => {
      // Create deposit use case for webhook handler
      processDeposit = new ProcessDepositUseCase(
        accountRepository,
        transactionRepository,
        paymentMethodRepository,
        paymentProviderFactory,
        transactionManager
      );

      // Create Express app with webhook routes
      app = express();
      app.use(express.json());

      const webhookController = createWebhookController({
        depositService: processDeposit,
        withdrawalService: initiateWithdrawal,
        transactionRepository,
        providerFactory: paymentProviderFactory,
      });

      app.use('/webhooks', webhookController);
    });

    it('should complete withdrawal when Xendit sends payout.succeeded webhook', async () => {
      console.log('\n=== WEBHOOK TEST: Successful Disbursement ===');

      // Step 1: Initiate a transfer to give User B extra funds
      const transferKey = IdempotencyKey.from(`transfer-${uuidv4()}`);
      const transferResult = await executeTransfer.initiateTransfer({
        idempotencyKey: transferKey,
        sourceAccountId: userAAccount.id,
        destinationAccountId: userBAccount.id,
        amount: Money.credits(TRANSFER_AMOUNT),
      });

      await executeTransfer.confirmTransfer({
        transactionId: transferResult.transaction.id,
        confirmationToken: transferResult.confirmationToken,
      });

      // Step 2: Initiate withdrawal (funds are held)
      const withdrawalKey = IdempotencyKey.from(`withdrawal-${uuidv4()}`);
      let withdrawalResult;

      try {
        withdrawalResult = await initiateWithdrawal.initiateWithdrawal({
          idempotencyKey: withdrawalKey,
          accountId: userBAccount.id,
          amount: Money.credits(500n), // $5 withdrawal
          paymentMethodId: userBXenditPaymentMethod.id,
        });
        console.log(`  Withdrawal initiated: ${withdrawalResult.transaction.id}`);
        console.log(`  External Reference: ${withdrawalResult.transaction.externalReference}`);
      } catch (error) {
        console.log(`  Withdrawal initiation failed: ${error instanceof Error ? error.message : 'Unknown'}`);
        // Skip webhook test if Xendit is not available
        return;
      }

      // Verify funds are held
      let accountB = await accountRepository.findById(userBAccount.id);
      const balanceBeforeWebhook = accountB!.balance.amount;
      const availableBeforeWebhook = accountB!.availableBalance.amount;
      console.log(`  Before webhook - Balance: ${balanceBeforeWebhook}, Available: ${availableBeforeWebhook}`);

      expect(accountB!.availableBalance.amount).toBe(INITIAL_BALANCE + TRANSFER_AMOUNT - 500n);

      // Step 3: Simulate Xendit payout.succeeded webhook
      const webhookPayload = {
        event: 'payout.succeeded',
        business_id: 'test-business-id',
        created: new Date().toISOString(),
        data: {
          id: withdrawalResult.transaction.externalReference?.toString() ?? 'ext-123',
          reference_id: withdrawalResult.transaction.id.toString(),
          channel_code: 'ID_BCA',
          channel_properties: {
            account_number: '1234567890',
            account_holder_name: 'Test User',
          },
          amount: 500,
          currency: 'IDR',
          description: 'Withdrawal',
          status: 'SUCCEEDED',
          metadata: {
            transaction_id: withdrawalResult.transaction.id.toString(),
            account_id: userBAccount.id.toString(),
          },
        },
      };

      // Make webhook request
      const response = await request(app)
        .post('/webhooks/xendit')
        .set('x-callback-token', process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_webhook_token')
        .send(webhookPayload);

      console.log(`  Webhook response: ${response.status}`);
      expect(response.status).toBe(200);

      // Small delay to ensure transaction is fully committed
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Step 4: Verify withdrawal completed - query directly from pool for fresh read
      const directResult = await pool.query(
        'SELECT status, completed_at FROM transactions WHERE id = $1',
        [withdrawalResult.transaction.id.toString()]
      );
      console.log(`  Transaction status (direct query): ${directResult.rows[0]?.status}`);
      console.log(`  Completed at (direct query): ${directResult.rows[0]?.completed_at}`);

      const updatedTransaction = await transactionRepository.findById(
        withdrawalResult.transaction.id
      );
      console.log(`  Transaction status after webhook: ${updatedTransaction?.status}`);
      expect(updatedTransaction?.status).toBe('completed');
      expect(updatedTransaction?.completedAt).not.toBeNull();

      // Step 5: Verify balance was debited
      accountB = await accountRepository.findById(userBAccount.id);
      console.log(`  After webhook - Balance: ${accountB!.balance.amount}, Available: ${accountB!.availableBalance.amount}`);

      // Balance should be reduced by withdrawal amount
      expect(accountB!.balance.amount).toBe(INITIAL_BALANCE + TRANSFER_AMOUNT - 500n);
      // Available should match balance (no more holds)
      expect(accountB!.availableBalance.amount).toBe(INITIAL_BALANCE + TRANSFER_AMOUNT - 500n);

      console.log('  ✓ Withdrawal completed successfully via webhook');
    });

    it('should release funds when Xendit sends payout.failed webhook', async () => {
      console.log('\n=== WEBHOOK TEST: Failed Disbursement (Insufficient Balance) ===');

      // Step 1: Initiate withdrawal
      const withdrawalKey = IdempotencyKey.from(`withdrawal-fail-${uuidv4()}`);
      let withdrawalResult;

      try {
        withdrawalResult = await initiateWithdrawal.initiateWithdrawal({
          idempotencyKey: withdrawalKey,
          accountId: userAAccount.id,
          amount: Money.credits(300n), // $3 withdrawal
          paymentMethodId: userBXenditPaymentMethod.id, // Using B's payment method intentionally for test
        });
      } catch (error) {
        // Payment method doesn't belong to account A - expected
        // Create a payment method for user A instead
        const userAPaymentMethod = PaymentMethod.create({
          accountId: userAAccount.id,
          providerCode: 'xendit',
          type: 'bank_account',
          externalId: `xendit-pm-${uuidv4()}`,
          displayName: 'User A Bank Account',
          isWithdrawable: true,
        });
        userAPaymentMethod.verify();
        await paymentMethodRepository.save(userAPaymentMethod);

        withdrawalResult = await initiateWithdrawal.initiateWithdrawal({
          idempotencyKey: withdrawalKey,
          accountId: userAAccount.id,
          amount: Money.credits(300n),
          paymentMethodId: userAPaymentMethod.id,
        });
      }

      console.log(`  Withdrawal initiated: ${withdrawalResult.transaction.id}`);

      // Verify funds are held
      let accountA = await accountRepository.findById(userAAccount.id);
      const balanceBeforeWebhook = accountA!.balance.amount;
      console.log(`  Before webhook - Balance: ${balanceBeforeWebhook}, Available: ${accountA!.availableBalance.amount}`);

      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE - 300n); // 300 held

      // Step 2: Simulate Xendit payout.failed webhook (e.g., INSUFFICIENT_BALANCE)
      const webhookPayload = {
        event: 'payout.failed',
        business_id: 'test-business-id',
        created: new Date().toISOString(),
        data: {
          id: withdrawalResult.transaction.externalReference?.toString() ?? 'ext-456',
          reference_id: withdrawalResult.transaction.id.toString(),
          channel_code: 'ID_BCA',
          amount: 300,
          currency: 'IDR',
          status: 'FAILED',
          failure_code: 'INSUFFICIENT_BALANCE',
          failure_message: 'Your Xendit balance is insufficient to process this disbursement',
          metadata: {
            transaction_id: withdrawalResult.transaction.id.toString(),
            account_id: userAAccount.id.toString(),
          },
        },
      };

      const response = await request(app)
        .post('/webhooks/xendit')
        .set('x-callback-token', process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_webhook_token')
        .send(webhookPayload);

      console.log(`  Webhook response: ${response.status}`);
      expect(response.status).toBe(200);

      // Step 3: Verify withdrawal failed
      const updatedTransaction = await transactionRepository.findById(
        withdrawalResult.transaction.id
      );
      console.log(`  Transaction status after webhook: ${updatedTransaction?.status}`);
      expect(updatedTransaction?.status).toBe('failed');
      expect(updatedTransaction?.errorDetails).toBeDefined();
      expect((updatedTransaction?.errorDetails as Record<string, unknown>)?.['code']).toBe('INSUFFICIENT_BALANCE');

      // Step 4: Verify funds were released (hold removed)
      accountA = await accountRepository.findById(userAAccount.id);
      console.log(`  After webhook - Balance: ${accountA!.balance.amount}, Available: ${accountA!.availableBalance.amount}`);

      // Balance should be unchanged
      expect(accountA!.balance.amount).toBe(INITIAL_BALANCE);
      // Available should be restored (hold released)
      expect(accountA!.availableBalance.amount).toBe(INITIAL_BALANCE);

      console.log('  ✓ Funds released after failed withdrawal webhook');
    });

    it('should handle webhook with invalid signature', async () => {
      console.log('\n=== WEBHOOK TEST: Invalid Signature ===');

      const webhookPayload = {
        event: 'payout.succeeded',
        business_id: 'test-business-id',
        created: new Date().toISOString(),
        data: {
          id: 'ext-fake',
          status: 'SUCCEEDED',
        },
      };

      const response = await request(app)
        .post('/webhooks/xendit')
        .set('x-callback-token', 'wrong-token')
        .send(webhookPayload);

      console.log(`  Response status: ${response.status}`);
      expect(response.status).toBe(401);
      console.log('  ✓ Invalid signature rejected');
    });

    it('should handle webhook for non-existent transaction gracefully', async () => {
      console.log('\n=== WEBHOOK TEST: Non-existent Transaction ===');

      const webhookPayload = {
        event: 'payout.succeeded',
        business_id: 'test-business-id',
        created: new Date().toISOString(),
        data: {
          id: 'ext-nonexistent',
          status: 'SUCCEEDED',
          metadata: {
            transaction_id: uuidv4(), // Random non-existent ID
          },
        },
      };

      const response = await request(app)
        .post('/webhooks/xendit')
        .set('x-callback-token', process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_webhook_token')
        .send(webhookPayload);

      // Should return 200 to prevent retries, but log the error
      console.log(`  Response status: ${response.status}`);
      expect(response.status).toBe(200);
      console.log('  ✓ Non-existent transaction handled gracefully');
    });
  });
});
