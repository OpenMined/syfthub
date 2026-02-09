/**
 * Authenticate User Use Case
 *
 * Handles user registration, login, and JWT token generation.
 */

import jwt from 'jsonwebtoken';
import crypto from 'crypto';
import { User } from '../../domain/entities/User';
import { UserRepository } from '../ports/output/UserRepository';
import { AccountRepository } from '../ports/output/AccountRepository';
import { Account } from '../../domain/entities/Account';
import { ApiTokenService } from '../ports/input/ApiTokenService';
import { ALL_TOKEN_SCOPES } from '../../domain/entities/ApiToken';
import { UserId } from '../../domain/value-objects/Identifiers';

export interface AuthConfig {
  jwtSecret: string;
  jwtIssuer: string;
  jwtAudience: string;
  jwtExpiresInSeconds: number;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResult {
  user: {
    id: string;
    email: string;
  };
  accessToken: string;
  expiresIn: number;
}

export interface ProvisionResult {
  user: {
    id: string;
    email: string;
  };
  account: {
    id: string;
    type: string;
    balance: {
      amount: string;
      currency: string;
    };
  };
  apiToken: {
    token: string;
    prefix: string;
    scopes: string[];
    expiresAt: string | null;
  };
}

export class EmailAlreadyExistsError extends Error {
  constructor(email: string) {
    super(`Email ${email} is already registered`);
    this.name = 'EmailAlreadyExistsError';
  }
}

export class InvalidCredentialsError extends Error {
  constructor() {
    super('Invalid email or password');
    this.name = 'InvalidCredentialsError';
  }
}

export class UserNotActiveError extends Error {
  constructor() {
    super('User account is not active');
    this.name = 'UserNotActiveError';
  }
}

export class AuthenticateUserUseCase {
  constructor(
    private readonly userRepository: UserRepository,
    private readonly accountRepository: AccountRepository,
    private readonly apiTokenService: ApiTokenService,
    private readonly config: AuthConfig
  ) {}

  /**
   * Register a new user
   */
  async register(request: RegisterRequest): Promise<AuthResult> {
    // Normalize email
    const email = request.email.toLowerCase().trim();

    // Check if email already exists
    if (await this.userRepository.emailExists(email)) {
      throw new EmailAlreadyExistsError(email);
    }

    // Hash password using crypto (avoiding bcrypt dependency issues)
    const passwordHash = await this.hashPassword(request.password);

    // Create user
    const user = User.create({
      email,
      passwordHash,
    });

    await this.userRepository.save(user);

    // Generate JWT
    const accessToken = this.generateJwt(user);

    return {
      user: {
        id: user.id,
        email: user.email,
      },
      accessToken,
      expiresIn: this.config.jwtExpiresInSeconds,
    };
  }

  /**
   * Login with email and password
   */
  async login(request: LoginRequest): Promise<AuthResult> {
    const email = request.email.toLowerCase().trim();

    // Find user
    const user = await this.userRepository.findByEmail(email);
    if (!user) {
      throw new InvalidCredentialsError();
    }

    // Check if user is active
    if (!user.isActive()) {
      throw new UserNotActiveError();
    }

    // Verify password
    const isValid = await this.verifyPassword(request.password, user.passwordHash);
    if (!isValid) {
      throw new InvalidCredentialsError();
    }

    // Generate JWT
    const accessToken = this.generateJwt(user);

    return {
      user: {
        id: user.id,
        email: user.email,
      },
      accessToken,
      expiresIn: this.config.jwtExpiresInSeconds,
    };
  }

  /**
   * Full provisioning: register, create account, generate API token
   * Used by SyftHub backend for auto-provisioning
   */
  async provision(request: RegisterRequest): Promise<ProvisionResult> {
    // First register the user
    const authResult = await this.register(request);
    const userId = UserId.from(authResult.user.id);

    // Create a default account for the user
    const account = Account.create({
      userId,
      type: 'user',
      metadata: { source: 'auto_provision' },
    });
    await this.accountRepository.save(account);

    // Create an API token with full permissions
    const tokenResult = await this.apiTokenService.createToken({
      userId,
      name: 'Auto-provisioned token',
      scopes: [...ALL_TOKEN_SCOPES],
      expiresInDays: 365, // 1 year
    });

    return {
      user: {
        id: authResult.user.id,
        email: authResult.user.email,
      },
      account: {
        id: account.id,
        type: account.type,
        balance: account.balance.toJSON(),
      },
      apiToken: {
        token: tokenResult.token,
        prefix: tokenResult.apiToken.prefix,
        scopes: tokenResult.apiToken.scopes,
        expiresAt: tokenResult.apiToken.expiresAt?.toISOString() ?? null,
      },
    };
  }

  private generateJwt(user: User): string {
    const payload = {
      sub: user.id,
      email: user.email,
      scope: [...ALL_TOKEN_SCOPES], // Full access for JWT users
    };

    return jwt.sign(payload, this.config.jwtSecret, {
      issuer: this.config.jwtIssuer,
      audience: this.config.jwtAudience,
      expiresIn: this.config.jwtExpiresInSeconds,
      jwtid: crypto.randomUUID(),
    });
  }

  /**
   * Hash password using PBKDF2 (Node.js crypto)
   * Format: iterations:salt:hash (all base64)
   */
  private async hashPassword(password: string): Promise<string> {
    const iterations = 100000;
    const keylen = 64;
    const digest = 'sha512';
    const salt = crypto.randomBytes(32);

    return new Promise((resolve, reject) => {
      crypto.pbkdf2(password, salt, iterations, keylen, digest, (err, derivedKey) => {
        if (err) reject(err);
        else resolve(`${iterations}:${salt.toString('base64')}:${derivedKey.toString('base64')}`);
      });
    });
  }

  /**
   * Verify password against stored hash
   */
  private async verifyPassword(password: string, storedHash: string): Promise<boolean> {
    const parts = storedHash.split(':');
    if (parts.length !== 3) return false;

    const iterations = parseInt(parts[0]!, 10);
    const salt = Buffer.from(parts[1]!, 'base64');
    const hash = Buffer.from(parts[2]!, 'base64');
    const keylen = hash.length;
    const digest = 'sha512';

    return new Promise((resolve, reject) => {
      crypto.pbkdf2(password, salt, iterations, keylen, digest, (err, derivedKey) => {
        if (err) reject(err);
        else resolve(crypto.timingSafeEqual(hash, derivedKey));
      });
    });
  }
}
