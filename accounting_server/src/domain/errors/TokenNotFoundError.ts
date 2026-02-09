/**
 * Token Not Found Error
 *
 * Thrown when an API token cannot be found by ID.
 */

import { DomainError } from './DomainError';

export class TokenNotFoundError extends DomainError {
  readonly code = 'token-not-found';
  readonly httpStatus = 404;

  constructor(tokenId: string) {
    super(`API token ${tokenId} not found`);
  }
}
