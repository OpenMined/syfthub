/**
 * Auth Controller
 *
 * HTTP handlers for authentication operations (register, login, provision).
 * These endpoints are public (no auth required).
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import {
  AuthenticateUserUseCase,
  EmailAlreadyExistsError,
  InvalidCredentialsError,
  UserNotActiveError,
} from '../../../application/use-cases/AuthenticateUser';

// Request validation schemas
const RegisterSchema = z.object({
  email: z.string().email('Invalid email format'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

const LoginSchema = z.object({
  email: z.string().email('Invalid email format'),
  password: z.string().min(1, 'Password is required'),
});

const ProvisionSchema = z.object({
  email: z.string().email('Invalid email format'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

export function createAuthController(
  authenticateUser: AuthenticateUserUseCase
): Router {
  const router = Router();

  /**
   * POST /auth/register - Register a new user
   */
  router.post('/register', async (req: Request, res: Response, next: NextFunction) => {
    try {
      // Validate request body
      const validation = RegisterSchema.safeParse(req.body);
      if (!validation.success) {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/validation-error',
          title: 'Validation Error',
          status: 422,
          detail: 'Request body validation failed',
          errors: validation.error.errors.map((e) => ({
            field: e.path.join('.'),
            message: e.message,
          })),
        });
        return;
      }

      const data = validation.data as { email: string; password: string };
      const result = await authenticateUser.register({
        email: data.email,
        password: data.password,
      });

      res.status(201).json({
        user: result.user,
        access_token: result.accessToken,
        token_type: 'Bearer',
        expires_in: result.expiresIn,
      });

    } catch (error) {
      if (error instanceof EmailAlreadyExistsError) {
        res.status(409).json({
          type: 'https://api.ledger.example.com/problems/email-exists',
          title: 'Email Already Exists',
          status: 409,
          detail: error.message,
        });
        return;
      }
      next(error);
    }
  });

  /**
   * POST /auth/login - Login with email and password
   */
  router.post('/login', async (req: Request, res: Response, next: NextFunction) => {
    try {
      // Validate request body
      const validation = LoginSchema.safeParse(req.body);
      if (!validation.success) {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/validation-error',
          title: 'Validation Error',
          status: 422,
          detail: 'Request body validation failed',
          errors: validation.error.errors.map((e) => ({
            field: e.path.join('.'),
            message: e.message,
          })),
        });
        return;
      }

      const data = validation.data as { email: string; password: string };
      const result = await authenticateUser.login({
        email: data.email,
        password: data.password,
      });

      res.status(200).json({
        user: result.user,
        access_token: result.accessToken,
        token_type: 'Bearer',
        expires_in: result.expiresIn,
      });

    } catch (error) {
      if (error instanceof InvalidCredentialsError) {
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/invalid-credentials',
          title: 'Invalid Credentials',
          status: 401,
          detail: error.message,
        });
        return;
      }
      if (error instanceof UserNotActiveError) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/user-not-active',
          title: 'User Not Active',
          status: 403,
          detail: error.message,
        });
        return;
      }
      next(error);
    }
  });

  /**
   * POST /auth/provision - Full provisioning (register + create account + API token)
   * Used by SyftHub backend for auto-provisioning during user registration
   */
  router.post('/provision', async (req: Request, res: Response, next: NextFunction) => {
    try {
      // Validate request body
      const validation = ProvisionSchema.safeParse(req.body);
      if (!validation.success) {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/validation-error',
          title: 'Validation Error',
          status: 422,
          detail: 'Request body validation failed',
          errors: validation.error.errors.map((e) => ({
            field: e.path.join('.'),
            message: e.message,
          })),
        });
        return;
      }

      const data = validation.data as { email: string; password: string };
      const result = await authenticateUser.provision({
        email: data.email,
        password: data.password,
      });

      res.status(201).json({
        user: result.user,
        account: result.account,
        api_token: {
          token: result.apiToken.token,
          prefix: result.apiToken.prefix,
          scopes: result.apiToken.scopes,
          expires_at: result.apiToken.expiresAt,
          warning: 'Store this token securely. It will not be shown again.',
        },
      });

    } catch (error) {
      if (error instanceof EmailAlreadyExistsError) {
        res.status(409).json({
          type: 'https://api.ledger.example.com/problems/email-exists',
          title: 'Email Already Exists',
          status: 409,
          detail: error.message,
        });
        return;
      }
      next(error);
    }
  });

  return router;
}
