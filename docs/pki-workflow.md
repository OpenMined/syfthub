# SyftHub PKI Workflow Architecture

## Overview
This document visualizes the PKI (Public Key Infrastructure) workflow for SyftHub, demonstrating how users discover datasites, validate identities, and interact across different PKI platforms.

## Complete PKI Workflow Diagram

```mermaid
graph TB
    subgraph "SyftHub PKI Platform"
        U1[User Alice<br/>alice@syfthub]
        U2[User Bob<br/>bob@syfthub]

        subgraph "SyftHub Server"
            REG[Registration<br/>Service]
            AUTH[Auth Service<br/>JWT + Ed25519]
            DISC[Discovery<br/>Service]
            DS_DIR[Datasite<br/>Directory]
            KEY_STORE[Public Key<br/>Registry]
        end

        subgraph "User Key Management"
            PRIV1[Alice Private Key<br/>Ed25519]
            PUB1[Alice Public Key<br/>Base64 Encoded]
            PRIV2[Bob Private Key<br/>Ed25519]
            PUB2[Bob Public Key<br/>Base64 Encoded]
        end
    end

    subgraph "External PKI Platform"
        U3[User Carol<br/>carol@otherpki]
        EXT_AUTH[External PKI<br/>Auth Service]
        EXT_KEY[Carol's Keys<br/>RSA/Ed25519]
    end

    subgraph "Datasites"
        DS1[Datasite A<br/>Public Dataset]
        DS2[Datasite B<br/>Private Research]
        DS3[Datasite C<br/>Organization Data]

        subgraph "Datasite PKI Validation"
            VAL1[Identity<br/>Validator A]
            VAL2[Identity<br/>Validator B]
            VAL3[Identity<br/>Validator C]

            TRUST[Trust Registry<br/>Accepted PKI Servers]
        end
    end

    %% Registration Flow
    U1 -.->|1. Register| REG
    REG -->|2. Generate<br/>Key Pair| AUTH
    AUTH -->|3. Store Public Key| KEY_STORE
    AUTH -->|4. Return Keys| U1
    U1 -->|5. Store Private Key<br/>Locally| PRIV1

    %% Discovery Flow
    U1 -->|6. Browse/Search| DISC
    DISC -->|7. Query| DS_DIR
    DS_DIR -->|8. Return Results| U1

    %% Identity Validation for Datasite Access
    U1 -->|9. Request Access<br/>+ Signature| DS1
    DS1 -->|10. Verify with| VAL1
    VAL1 -->|11. Fetch Public Key| KEY_STORE
    KEY_STORE -->|12. Return Key| VAL1
    VAL1 -->|13. Validate Signature| DS1
    DS1 -->|14. Grant Access| U1

    %% Cross-Platform PKI
    U3 -->|A. Authenticate| EXT_AUTH
    EXT_AUTH -->|B. Issue Certificate| U3
    U3 -->|C. Request Access<br/>+ Certificate| DS2
    DS2 -->|D. Check| VAL2
    VAL2 -->|E. Verify with| TRUST
    TRUST -->|F. Validate External PKI| EXT_AUTH
    EXT_AUTH -->|G. Confirm Identity| VAL2
    VAL2 -->|H. Grant Access| DS2
    DS2 -->|I. Provide Data| U3

    %% Mutual Authentication
    U2 <-->|Sign & Verify| U1

    style U1 fill:#e1f5e1
    style U2 fill:#e1f5e1
    style U3 fill:#ffe1e1
    style DS1 fill:#e1e1ff
    style DS2 fill:#e1e1ff
    style DS3 fill:#e1e1ff
    style KEY_STORE fill:#fff3e1
    style TRUST fill:#fff3e1
```

## Detailed Workflow Steps

### User Registration & Key Generation
```mermaid
sequenceDiagram
    participant User
    participant SyftHub
    participant KeyGen
    participant Registry

    User->>SyftHub: POST /api/v1/register
    SyftHub->>KeyGen: Generate Ed25519 Key Pair
    KeyGen-->>SyftHub: Private Key + Public Key
    SyftHub->>Registry: Store Public Key
    SyftHub-->>User: Return Credentials + Keys
    User->>User: Secure Private Key Storage

    Note over User: User now has:<br/>- JWT tokens for API access<br/>- Ed25519 key pair for signing
```

### Datasite Discovery & Access
```mermaid
sequenceDiagram
    participant User
    participant Discovery
    participant Datasite
    participant Validator
    participant PKI_Registry

    User->>Discovery: GET /api/v1/datasites/public
    Discovery-->>User: List of Available Datasites

    User->>User: Select Datasite
    User->>User: Sign Request with Private Key

    User->>Datasite: Request Access + Signature
    Datasite->>Validator: Verify Identity
    Validator->>PKI_Registry: Fetch User Public Key
    PKI_Registry-->>Validator: Public Key
    Validator->>Validator: Verify Signature

    alt Signature Valid
        Validator-->>Datasite: Identity Confirmed
        Datasite-->>User: Grant Access Token
    else Signature Invalid
        Validator-->>Datasite: Identity Failed
        Datasite-->>User: Access Denied
    end
```

### Cross-Platform PKI Integration
```mermaid
flowchart LR
    subgraph "PKI Federation"
        SH[SyftHub PKI]
        KH[Keybase PKI]
        GH[GitHub PKI]
        CS[Custom PKI Server]
    end

    subgraph "Trust Management"
        TR[Trust Registry]
        WL[Whitelist]
        VP[Validation Policies]
    end

    subgraph "Datasite Configuration"
        DS[Datasite]
        AC[Access Control]
        PKI_SEL[PKI Selector]
    end

    SH --> TR
    KH --> TR
    GH --> TR
    CS --> TR

    TR --> WL
    WL --> VP
    VP --> AC

    DS --> PKI_SEL
    PKI_SEL --> AC

    style SH fill:#90EE90
    style TR fill:#FFE4B5
    style DS fill:#ADD8E6
```

## Security Features

### Multi-Factor Authentication Flow
```mermaid
graph LR
    subgraph "Authentication Layers"
        L1[Layer 1:<br/>Password/JWT]
        L2[Layer 2:<br/>Ed25519 Signature]
        L3[Layer 3:<br/>Optional TOTP]
    end

    subgraph "Verification"
        V1[Verify JWT]
        V2[Verify Signature]
        V3[Verify TOTP]
    end

    subgraph "Access Decision"
        ALLOW[Grant Access]
        DENY[Deny Access]
    end

    L1 --> V1
    L2 --> V2
    L3 --> V3

    V1 --> |Valid| V2
    V1 --> |Invalid| DENY
    V2 --> |Valid| V3
    V2 --> |Invalid| DENY
    V3 --> |Valid| ALLOW
    V3 --> |Invalid| DENY
    V3 --> |Not Required| ALLOW
```

## PKI Trust Model

### Trust Relationship Network
```mermaid
graph TB
    subgraph "Trust Levels"
        FULL[Full Trust<br/>Same PKI Server]
        FED[Federated Trust<br/>Partner PKI]
        COND[Conditional Trust<br/>Verified External]
        ZERO[Zero Trust<br/>Unknown PKI]
    end

    subgraph "Access Permissions"
        PUB_ACC[Public Access<br/>No Auth Required]
        INT_ACC[Internal Access<br/>Same Org/PKI]
        PRIV_ACC[Private Access<br/>Explicit Permission]
        DENY_ACC[Denied<br/>No Trust]
    end

    FULL --> PRIV_ACC
    FULL --> INT_ACC
    FULL --> PUB_ACC

    FED --> INT_ACC
    FED --> PUB_ACC

    COND --> PUB_ACC
    COND -.->|With Approval| INT_ACC

    ZERO --> PUB_ACC
    ZERO --> DENY_ACC

    style FULL fill:#90EE90
    style FED fill:#87CEEB
    style COND fill:#FFE4B5
    style ZERO fill:#FFB6C1
```

## Implementation Notes

1. **Key Generation**: Ed25519 keys are generated server-side during registration
2. **Key Storage**: Public keys stored in database, private keys returned to user
3. **Signature Verification**: `/api/v1/users/verify-signature` endpoint validates signatures
4. **Cross-PKI Support**: Datasites can configure trusted PKI servers
5. **Identity Federation**: Support for multiple PKI providers through trust registry
6. **Access Control**: Three-tier visibility (public, internal, private)
7. **Audit Trail**: All authentication attempts logged for security

## Benefits of This Architecture

- **Decentralized Trust**: Users can bring their own PKI identities
- **Flexible Authentication**: Support for multiple PKI providers
- **Strong Identity**: Cryptographic proof of identity
- **Privacy Preserving**: Users control their private keys
- **Interoperability**: Works across different PKI platforms
- **Scalability**: Federation reduces central authority burden
