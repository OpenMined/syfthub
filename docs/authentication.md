# Authentication Guide

This document describes the OAuth2/JWT authentication system implemented in Syfthub API.

## Overview

The API uses JWT tokens for authentication with the following features:
- **Access tokens**: Short-lived (30 minutes) for API access
- **Refresh tokens**: Long-lived (7 days) for token renewal
- **Role-based access control**: Admin, User, and Guest roles
- **Token blacklisting**: Logout functionality invalidates tokens
- **Secure password hashing**: Argon2 algorithm

## Authentication Flow

### 1. User Registration

```bash
POST /api/v1/auth/register
Content-Type: application/json

{
  "username": "johndoe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "password": "securepassword123",
  "age": 30
}
```

Response:
```json
{
  "user": {
    "id": 1,
    "username": "johndoe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "role": "user",
    "is_active": true
  },
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### 2. User Login

```bash
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

username=johndoe&password=securepassword123
```

You can also login with email instead of username.

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### 3. Accessing Protected Endpoints

Include the access token in the Authorization header:

```bash
GET /api/v1/auth/me
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

### 4. Token Refresh

When the access token expires, use the refresh token:

```bash
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### 5. Password Change

```bash
PUT /api/v1/auth/me/password
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "current_password": "oldpassword",
  "new_password": "newsecurepassword123"
}
```

### 6. Logout

```bash
POST /api/v1/auth/logout
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

This blacklists the current access token.

## Protected vs Public Endpoints

### Authentication Required
- `POST /api/v1/auth/logout` - Logout
- `GET /api/v1/auth/me` - Get current user profile
- `PUT /api/v1/auth/me/password` - Change password
- `POST /api/v1/items` - Create item
- `PUT /api/v1/items/{item_id}` - Update item (owner or admin)
- `DELETE /api/v1/items/{item_id}` - Delete item (owner or admin)
- `GET /api/v1/users` - List users (admin only)
- `GET /api/v1/users/{user_id}` - Get user (self or admin)
- `PUT /api/v1/users/{user_id}` - Update user (self or admin)
- `DELETE /api/v1/users/{user_id}` - Delete user (self or admin)

### Public Access
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/refresh` - Token refresh
- `GET /api/v1/items` - List items (public items only without auth)
- `GET /api/v1/items/{item_id}` - Get item (if public or authenticated)
- `GET /` - Root endpoint
- `/health` - Health check

## User Roles

### Guest
- Can only access public endpoints
- Cannot create or modify resources

### User (Default)
- Can create items and manage own resources
- Can view public items and own private items
- Can update own profile

### Admin
- Full access to all resources
- Can manage any user or item
- Can access admin-only endpoints

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Could not validate credentials"
}
```

### 403 Forbidden
```json
{
  "detail": "Operation not permitted"
}
```

### 400 Bad Request
```json
{
  "detail": "Username already registered"
}
```

## Security Features

1. **Password Security**: Argon2 hashing with automatic salt
2. **JWT Security**: HS256 algorithm with configurable expiration
3. **Token Rotation**: New refresh token issued on each refresh
4. **Token Blacklisting**: Logout invalidates tokens
5. **Role-based Access**: Granular permission control
6. **Input Validation**: Pydantic models validate all requests

## Configuration

Key settings in `src/syfthub/core/config.py`:

- `secret_key`: JWT signing key (change in production!)
- `access_token_expire_minutes`: 30 minutes default
- `refresh_token_expire_days`: 7 days default
- `password_min_length`: 8 characters minimum

## Best Practices

1. Store tokens securely in client applications
2. Handle token expiration gracefully with refresh logic
3. Always use HTTPS in production
4. Implement proper logout flows
5. Monitor for suspicious authentication patterns
6. Regularly rotate the JWT secret key
7. Use environment variables for sensitive configuration

## Development vs Production

### Development
- Uses in-memory storage for users and token blacklist
- Default secret key for convenience
- Detailed error messages

### Production Considerations
- Use real database for user storage
- Secure secret key from environment
- Rate limiting on auth endpoints
- Logging and monitoring
- HTTPS-only communication
