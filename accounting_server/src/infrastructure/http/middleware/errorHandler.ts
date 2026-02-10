/**
 * Global Error Handler Middleware
 *
 * Catches all unhandled errors and formats them as RFC 9457 Problem Details.
 */

import { Request, Response, NextFunction } from 'express';
import { DomainError } from '../../../domain/errors/DomainError';

export function errorHandler(
  error: Error,
  req: Request,
  res: Response,
  _next: NextFunction
): void {
  // Log the error
  console.error('Unhandled error:', {
    name: error.name,
    message: error.message,
    stack: error.stack,
    path: req.path,
    method: req.method,
  });

  // Handle domain errors
  if (error instanceof DomainError) {
    res.status(error.httpStatus).json(error.toProblemDetails(req.path));
    return;
  }

  // Handle validation errors from zod
  if (error.name === 'ZodError') {
    res.status(422).json({
      type: 'https://api.ledger.example.com/problems/validation-error',
      title: 'Validation Error',
      status: 422,
      detail: 'Request validation failed',
      instance: req.path,
    });
    return;
  }

  // Handle PostgreSQL errors
  if ('code' in error && typeof (error as { code: unknown }).code === 'string') {
    const pgError = error as { code: string; detail?: string };

    // Unique violation
    if (pgError.code === '23505') {
      res.status(409).json({
        type: 'https://api.ledger.example.com/problems/conflict',
        title: 'Conflict',
        status: 409,
        detail: 'A resource with this identifier already exists',
        instance: req.path,
      });
      return;
    }

    // Foreign key violation
    if (pgError.code === '23503') {
      res.status(422).json({
        type: 'https://api.ledger.example.com/problems/reference-error',
        title: 'Reference Error',
        status: 422,
        detail: 'Referenced resource does not exist',
        instance: req.path,
      });
      return;
    }

    // Serialization failure
    if (pgError.code === '40001') {
      res.status(409).json({
        type: 'https://api.ledger.example.com/problems/serialization-failure',
        title: 'Serialization Failure',
        status: 409,
        detail: 'The operation conflicted with another transaction. Please retry.',
        instance: req.path,
      });
      return;
    }
  }

  // Default to 500 Internal Server Error
  res.status(500).json({
    type: 'https://api.ledger.example.com/problems/internal-error',
    title: 'Internal Server Error',
    status: 500,
    detail: 'An unexpected error occurred. Please try again later.',
    instance: req.path,
    // Don't expose error details in production
    ...(process.env.NODE_ENV === 'development' && {
      debug: {
        name: error.name,
        message: error.message,
      },
    }),
  });
}

/**
 * 404 Not Found handler for unmatched routes
 */
export function notFoundHandler(req: Request, res: Response): void {
  res.status(404).json({
    type: 'https://api.ledger.example.com/problems/not-found',
    title: 'Not Found',
    status: 404,
    detail: `The requested resource ${req.path} was not found`,
    instance: req.path,
  });
}
