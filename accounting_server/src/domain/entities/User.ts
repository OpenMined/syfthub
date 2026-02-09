/**
 * User Entity
 *
 * Represents a user in the ledger system for authentication purposes.
 */

import { UserId } from '../value-objects/Identifiers';

export type UserStatus = 'active' | 'suspended' | 'deleted';

export interface UserProps {
  id: UserId;
  email: string;
  passwordHash: string;
  status: UserStatus;
  createdAt: Date;
  updatedAt: Date;
}

export interface CreateUserProps {
  email: string;
  passwordHash: string;
}

export class User {
  readonly id: UserId;
  readonly email: string;
  readonly passwordHash: string;
  readonly status: UserStatus;
  readonly createdAt: Date;
  readonly updatedAt: Date;

  private constructor(props: UserProps) {
    this.id = props.id;
    this.email = props.email;
    this.passwordHash = props.passwordHash;
    this.status = props.status;
    this.createdAt = props.createdAt;
    this.updatedAt = props.updatedAt;
  }

  static create(props: CreateUserProps): User {
    const now = new Date();
    return new User({
      id: UserId.generate(),
      email: props.email.toLowerCase().trim(),
      passwordHash: props.passwordHash,
      status: 'active',
      createdAt: now,
      updatedAt: now,
    });
  }

  static reconstitute(props: UserProps): User {
    return new User(props);
  }

  isActive(): boolean {
    return this.status === 'active';
  }

  toJSON() {
    return {
      id: this.id,
      email: this.email,
      status: this.status,
      createdAt: this.createdAt.toISOString(),
      updatedAt: this.updatedAt.toISOString(),
    };
  }
}
