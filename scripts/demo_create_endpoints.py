#!/usr/bin/env python3
"""
SyftHub Full Stack Demo Script: Create Endpoints in SyftAI-Space and Register in SyftHub

This script demonstrates the complete workflow:
1. Creates synthetic finance news documents for RAG
2. Creates a Dataset in SyftAI-Space (Weaviate is auto-provisioned)
3. Creates model instances in SyftAI-Space (OpenAI models)
4. Creates RAG endpoints in SyftAI-Space (combining models + datasets)
5. Registers those endpoints in SyftHub with connection URLs pointing to SyftAI-Space
6. The aggregator can then call SyftAI-Space endpoints using the URL + slug

Architecture:
    - SyftHub (backend, frontend, aggregator, nginx) runs in Docker on port 8080
    - SyftAI-Space runs locally on the host machine at port 8085
    - SyftAI-Space auto-provisions Weaviate when a dataset is created
    - Aggregator reaches SyftAI-Space via host.docker.internal:8085

Usage:
    # 1. Start Docker services (SyftHub only)
    docker compose -f docker-compose.fullstack.yml up --build -d

    # 2. Start SyftAI-Space locally (in another terminal)
    cd SyftAI-Space
    source .venv/bin/activate
    export OPENAI_API_KEY=sk-...
    uvicorn syftai_space.main:app --reload --host 0.0.0.0 --port 8085

    # 3. Run this script to seed endpoints
    cd sdk/python
    export SYFTHUB_URL=http://localhost:8080
    export SYFTAI_SPACE_URL=http://localhost:8085
    export OPENAI_API_KEY=sk-...
    uv run python ../../scripts/demo_create_endpoints.py

Requirements:
    - SyftHub Python SDK (syfthub-sdk)
    - Running SyftHub backend at SYFTHUB_URL (default: http://localhost:8080)
    - Running SyftAI-Space backend at SYFTAI_SPACE_URL (default: http://localhost:8085)
    - OpenAI API key for model creation
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from syfthub_sdk import (
    AuthenticationError,
    Connection,
    EndpointType,
    Policy,
    SyftHubClient,
    SyftHubError,
    ValidationError,
    Visibility,
)


def generate_unique_id() -> str:
    """Generate a short unique ID for usernames and slugs."""
    return uuid.uuid4().hex[:8]


# ============================================================================
# Synthetic Document Collections
# ============================================================================

FINANCE_NEWS_DOCUMENTS = [
    {
        "filename": "tech_earnings_q4.md",
        "content": """Tech Giants Report Strong Q4 Earnings

Major technology companies have reported stronger-than-expected fourth quarter earnings,
driven by continued growth in cloud computing and artificial intelligence services.

Apple Inc. reported revenue of $119.6 billion, exceeding analyst expectations of $117.9 billion.
The company's services segment, including the App Store and Apple Music, grew 11% year-over-year.

Microsoft Corporation posted quarterly revenue of $62.0 billion, a 17% increase from the
previous year. Azure cloud services saw 28% growth, while the company's AI investments
continue to show promising returns.

Amazon's AWS division generated $24.2 billion in revenue, maintaining its position as the
leading cloud infrastructure provider. The company's advertising business also showed
strong growth at 26% year-over-year.

Google parent Alphabet reported $86.3 billion in revenue, with search advertising
remaining the primary revenue driver despite increased competition in the AI space.

Analysts suggest these results indicate sustained enterprise spending on digital
transformation initiatives, with particular emphasis on generative AI capabilities."""
    },
    {
        "filename": "fed_interest_rates.md",
        "content": """Federal Reserve Signals Potential Rate Cuts in 2024

The Federal Reserve indicated a more dovish stance in its latest policy meeting,
suggesting that interest rate cuts could be on the horizon if inflation continues
to moderate.

Fed Chair Jerome Powell stated that the central bank is closely monitoring economic
data and remains committed to achieving the 2% inflation target. Recent Consumer
Price Index (CPI) data showed inflation cooling to 3.1%, down from a peak of 9.1%
in June 2022.

Key points from the FOMC meeting:
- Federal funds rate maintained at 5.25-5.50%
- Three rate cuts projected for 2024
- Balance sheet reduction to continue at current pace
- Labor market remains resilient but showing signs of cooling

Market participants responded positively, with the S&P 500 rising 1.4% following
the announcement. Bond yields fell across the curve, with the 10-year Treasury
yield dropping to 3.87%.

Economists at major investment banks are now pricing in 100-150 basis points of
cuts over the next 18 months, though the Fed emphasized data dependence."""
    },
    {
        "filename": "crypto_market_update.md",
        "content": """Cryptocurrency Market Sees Institutional Adoption Surge

The cryptocurrency market has experienced significant institutional interest following
the approval of spot Bitcoin ETFs by the Securities and Exchange Commission (SEC).

Bitcoin (BTC) reached new all-time highs above $73,000, driven by inflows into newly
approved exchange-traded funds. BlackRock's iShares Bitcoin Trust (IBIT) accumulated
over $10 billion in assets within its first two months of trading.

Key market developments:
- Total crypto market cap exceeds $2.5 trillion
- Ethereum (ETH) trading above $4,000 amid ETF speculation
- Institutional custody solutions seeing record adoption
- Regulatory clarity improving in major markets

Major financial institutions are expanding their cryptocurrency offerings:
- Fidelity launched crypto custody services for institutional clients
- JPMorgan introduced blockchain-based payment systems
- Goldman Sachs restarted its crypto trading desk

However, analysts caution that market volatility remains elevated, and regulatory
developments continue to pose risks. The upcoming Bitcoin halving event, expected
in April, is anticipated to reduce new supply and potentially support prices."""
    },
    {
        "filename": "global_markets_asia.md",
        "content": """Asian Markets Rally on China Stimulus Measures

Asian equity markets posted strong gains following the announcement of new economic
stimulus measures by Chinese authorities aimed at stabilizing the property sector
and boosting consumer confidence.

The People's Bank of China (PBOC) announced:
- 25 basis point cut to the reserve requirement ratio (RRR)
- New lending facilities for property developers totaling 1 trillion yuan
- Extended support for struggling real estate companies
- Consumer voucher programs to stimulate domestic spending

Market reactions across the region:
- Shanghai Composite Index +3.2%
- Hang Seng Index +4.1%
- Nikkei 225 +1.8%
- KOSPI +2.1%

Japan's market also benefited from corporate governance reforms pushing companies
to improve shareholder returns. The weak yen, trading above 150 per dollar,
continued to support export-oriented sectors.

Analysts at Morgan Stanley raised their China GDP growth forecast to 5.2% for the
year, citing the impact of stimulus measures. However, structural challenges in
the property sector remain a concern for long-term economic stability."""
    },
    {
        "filename": "sustainable_investing.md",
        "content": """ESG Investing Reaches $40 Trillion in Global Assets

Environmental, Social, and Governance (ESG) investing has continued its rapid growth,
with global sustainable investment assets now exceeding $40 trillion according to
the Global Sustainable Investment Alliance.

Key trends in sustainable finance:
- Climate-focused funds attracted $50 billion in new flows
- Green bond issuance reached record $600 billion annually
- Corporate sustainability reporting becoming mandatory in EU
- Net-zero commitments from major asset managers accelerating

Major developments in the sector:
- BlackRock expanded its sustainable fund offerings to 200+ products
- Vanguard faced pressure over climate voting policies
- SEC proposed enhanced climate disclosure rules
- EU Taxonomy implementation driving investment decisions

The energy transition is creating significant investment opportunities:
- Renewable energy capacity additions hit 500 GW globally
- Electric vehicle sales exceeded 14 million units
- Battery storage investments reached $20 billion
- Green hydrogen projects in development pipeline

Critics argue that ESG ratings lack standardization, and greenwashing remains
a concern. However, institutional investors increasingly view sustainability
factors as material to long-term financial performance."""
    },
]

TECH_DOCS_DOCUMENTS = [
    {
        "filename": "api_best_practices.md",
        "content": """RESTful API Design Best Practices

Building well-designed APIs is crucial for creating scalable and maintainable
software systems. This guide covers essential best practices for RESTful API design.

Resource Naming Conventions:
- Use nouns for resource names (e.g., /users, /products, /orders)
- Use plural forms consistently (/users not /user)
- Use hyphens for multi-word resources (/user-profiles)
- Avoid verbs in URLs; let HTTP methods convey actions

HTTP Methods:
- GET: Retrieve resources (idempotent, safe)
- POST: Create new resources
- PUT: Update/replace entire resource
- PATCH: Partial update of resource
- DELETE: Remove resource

Status Codes:
- 200 OK: Successful GET, PUT, PATCH
- 201 Created: Successful POST
- 204 No Content: Successful DELETE
- 400 Bad Request: Invalid input
- 401 Unauthorized: Authentication required
- 403 Forbidden: Insufficient permissions
- 404 Not Found: Resource doesn't exist
- 429 Too Many Requests: Rate limit exceeded
- 500 Internal Server Error: Server-side error

Pagination:
For large collections, implement cursor-based or offset pagination.
Example: GET /api/v1/users?limit=20&offset=40

Versioning:
Include version in URL path (/api/v1/) or Accept header.
Always maintain backward compatibility within major versions."""
    },
    {
        "filename": "authentication_patterns.md",
        "content": """Modern Authentication Patterns for Web Applications

Authentication is a critical component of application security. This document
covers the most common authentication patterns used in modern web development.

JWT (JSON Web Tokens):
JWTs are self-contained tokens that encode user information and claims.
Structure: header.payload.signature (Base64 encoded)

Advantages:
- Stateless: No server-side session storage needed
- Scalable: Works well in distributed systems
- Cross-domain: Can be used across different services

Best Practices:
- Set short expiration times (15-60 minutes)
- Use refresh tokens for session extension
- Store in httpOnly cookies to prevent XSS
- Include only necessary claims in payload

OAuth 2.0 Flows:
1. Authorization Code Flow (with PKCE) - For web/mobile apps
2. Client Credentials Flow - For machine-to-machine
3. Device Authorization Flow - For limited input devices

OpenID Connect (OIDC):
An identity layer built on OAuth 2.0 that provides:
- ID tokens with user identity information
- UserInfo endpoint for profile data
- Standardized scopes (openid, profile, email)

Session Management:
- Implement secure session cookies (Secure, HttpOnly, SameSite)
- Set appropriate session timeouts
- Provide logout functionality that invalidates tokens
- Consider implementing session binding to prevent hijacking"""
    },
    {
        "filename": "database_optimization.md",
        "content": """Database Performance Optimization Techniques

Optimizing database performance is essential for building responsive applications.
This guide covers key strategies for improving query performance and scalability.

Indexing Strategies:
- Create indexes on columns used in WHERE, JOIN, ORDER BY
- Use composite indexes for multi-column queries
- Consider covering indexes to avoid table lookups
- Monitor index usage and remove unused indexes

Index Types:
- B-tree: General purpose, good for range queries
- Hash: Equality comparisons only, very fast
- GiST/GIN: Full-text search, geometric data
- BRIN: Large tables with natural ordering

Query Optimization:
- Use EXPLAIN ANALYZE to understand query plans
- Avoid SELECT * - specify needed columns
- Use JOINs instead of subqueries when possible
- Limit result sets with appropriate WHERE clauses

Connection Pooling:
- Use connection pools (PgBouncer, HikariCP)
- Size pools based on workload (connections = cores * 2 + disk spindles)
- Monitor pool utilization and adjust

Caching Strategies:
- Application-level caching (Redis, Memcached)
- Query result caching
- Object caching for frequently accessed data
- Cache invalidation strategies (TTL, event-based)

Sharding and Partitioning:
- Horizontal partitioning: Split tables by row ranges
- Vertical partitioning: Split tables by columns
- Sharding: Distribute data across multiple databases
- Consider read replicas for read-heavy workloads"""
    },
    {
        "filename": "microservices_architecture.md",
        "content": """Microservices Architecture Patterns

Microservices architecture enables building scalable, maintainable systems
by decomposing applications into small, independent services.

Core Principles:
- Single Responsibility: Each service handles one business capability
- Loose Coupling: Services are independent and communicate via APIs
- High Cohesion: Related functionality grouped together
- Autonomous: Teams can develop, deploy, scale independently

Communication Patterns:
1. Synchronous (REST, gRPC)
   - Request-response model
   - Simpler to implement and debug
   - Can create coupling and latency issues

2. Asynchronous (Message Queues)
   - Event-driven architecture
   - Better resilience and scalability
   - Eventual consistency

Service Discovery:
- Client-side discovery (Netflix Eureka)
- Server-side discovery (Kubernetes Services)
- Service mesh (Istio, Linkerd)

Circuit Breaker Pattern:
Prevent cascade failures when services are unavailable:
- Closed: Normal operation, requests pass through
- Open: Service failing, reject requests immediately
- Half-Open: Test if service recovered

API Gateway:
- Single entry point for clients
- Request routing and load balancing
- Authentication and rate limiting
- Request/response transformation

Data Management:
- Database per service pattern
- Saga pattern for distributed transactions
- Event sourcing for audit trails
- CQRS for read/write optimization"""
    },
    {
        "filename": "cicd_pipelines.md",
        "content": """CI/CD Pipeline Best Practices

Continuous Integration and Continuous Deployment (CI/CD) automates the software
delivery process, enabling faster and more reliable releases.

Continuous Integration:
- Commit code frequently (at least daily)
- Automated build on every commit
- Run unit tests automatically
- Static code analysis and linting
- Security scanning (SAST, dependency checks)

Pipeline Stages:
1. Build: Compile code, create artifacts
2. Test: Unit, integration, e2e tests
3. Security: Vulnerability scanning
4. Deploy to Staging: Automated deployment
5. Acceptance Tests: User acceptance testing
6. Deploy to Production: With approval gates

Deployment Strategies:
- Rolling Update: Gradual replacement of instances
- Blue-Green: Switch traffic between environments
- Canary: Route small percentage to new version
- Feature Flags: Enable features for specific users

Infrastructure as Code:
- Terraform for cloud resources
- Kubernetes manifests for container orchestration
- Helm charts for application packaging
- GitOps with ArgoCD or Flux

Monitoring and Observability:
- Metrics collection (Prometheus, Datadog)
- Log aggregation (ELK Stack, Loki)
- Distributed tracing (Jaeger, Zipkin)
- Alerting and incident response

Best Practices:
- Keep pipelines fast (< 10 minutes)
- Fail fast - run fastest tests first
- Parallelize test execution
- Cache dependencies and build artifacts
- Implement rollback mechanisms
- Document pipeline configuration"""
    },
]

CLIMATE_RESEARCH_DOCUMENTS = [
    {
        "filename": "climate_science_fundamentals.md",
        "content": """Climate Science Fundamentals

Understanding the basic science of climate change is essential for informed decision-making
and policy development. This document covers the core concepts of climate science.

The Greenhouse Effect:
The greenhouse effect is a natural process that warms the Earth's surface. When the Sun's
energy reaches the atmosphere, some is reflected back to space and the rest is absorbed
and re-radiated by greenhouse gases. These gases include water vapor, carbon dioxide,
methane, nitrous oxide, and ozone. Human activities have increased concentrations of
these gases, enhancing the natural greenhouse effect.

The Carbon Cycle:
Carbon moves between the atmosphere, oceans, soil, and living organisms through various
processes. Natural sources include volcanic emissions, decomposition, and ocean release.
Natural sinks include photosynthesis, ocean absorption, and soil storage. Human activities
have disrupted this balance primarily through fossil fuel combustion and deforestation.

Global Temperature Trends:
Scientists measure global temperature through multiple methods including surface weather
stations, ocean buoys, satellites, and paleoclimate proxies. These measurements show
a clear warming trend, particularly accelerating in recent decades. Temperature changes
vary by region, with polar areas experiencing more pronounced warming.

Climate Modeling:
Climate models are sophisticated computer simulations that represent the interactions
between atmosphere, oceans, land surface, and ice. Models are validated against historical
data and used to project future scenarios. Different emission pathways lead to different
projected outcomes, informing policy decisions.

Attribution Science:
Attribution science determines the extent to which specific weather events or trends
can be linked to climate change versus natural variability. This field has advanced
significantly, allowing scientists to quantify how climate change affects the probability
and intensity of extreme events."""
    },
    {
        "filename": "renewable_energy_technologies.md",
        "content": """Renewable Energy Technologies Overview

The transition to renewable energy is a cornerstone of climate change mitigation.
This document provides an overview of major renewable energy technologies and their
current state of development.

Solar Energy:
Solar photovoltaic (PV) systems convert sunlight directly into electricity using
semiconductor materials. Efficiency has improved dramatically while costs have fallen.
Concentrated solar power (CSP) uses mirrors to focus sunlight and generate heat for
electricity production. Both utility-scale and distributed rooftop installations
contribute to the energy mix.

Wind Energy:
Wind turbines convert kinetic energy from wind into electricity. Onshore wind is now
one of the cheapest forms of electricity generation in many regions. Offshore wind
offers higher and more consistent wind speeds, though with higher installation costs.
Floating offshore platforms are expanding the potential deployment areas.

Hydroelectric Power:
Hydropower harnesses the energy of flowing water. Large reservoir systems provide
baseload power and energy storage capabilities. Run-of-river systems have lower
environmental impact but less flexibility. Pumped hydro storage remains the dominant
form of grid-scale energy storage globally.

Geothermal Energy:
Geothermal systems tap heat from the Earth's interior. Conventional systems require
specific geological conditions, while enhanced geothermal systems can expand viable
locations. Geothermal provides reliable baseload power with minimal land footprint.

Energy Storage:
Battery storage, particularly lithium-ion technology, enables integration of variable
renewable sources. Other storage technologies include flow batteries, compressed air,
and hydrogen. Storage addresses intermittency challenges and provides grid services.

Grid Integration:
Modern grids must accommodate variable renewable generation through improved forecasting,
demand response, interconnections, and flexible backup capacity. Smart grid technologies
enable better coordination between generation and consumption."""
    },
    {
        "filename": "carbon_capture_storage.md",
        "content": """Carbon Capture and Storage Technologies

Carbon capture and storage (CCS) and carbon dioxide removal (CDR) technologies are
increasingly recognized as necessary components of climate mitigation strategies.
This document covers the main approaches and their current status.

Point-Source Capture:
Industrial facilities and power plants can capture CO2 before it enters the atmosphere.
Post-combustion capture removes CO2 from flue gases using chemical solvents. Pre-combustion
capture converts fuel to hydrogen and CO2 before combustion. Oxy-fuel combustion uses
pure oxygen, producing a concentrated CO2 stream. Each approach has different efficiency
and cost characteristics.

Direct Air Capture:
Direct air capture (DAC) technologies remove CO2 directly from ambient air. This approach
can address distributed emissions and historical emissions. Current methods use either
liquid solvents or solid sorbents. Energy requirements and costs remain significant
challenges, though both are decreasing with technological advancement.

Geological Storage:
Captured CO2 can be stored in deep geological formations. Suitable formations include
depleted oil and gas reservoirs, deep saline aquifers, and unmineable coal seams.
Site selection requires careful geological assessment to ensure long-term containment.
Monitoring systems track stored CO2 behavior over time.

Carbon Utilization:
Captured CO2 can be used in various applications. Enhanced oil recovery has been the
primary commercial use. Emerging applications include building materials, synthetic
fuels, chemicals, and enhanced plant growth in greenhouses. Utilization can offset
capture costs but must be evaluated for net climate benefit.

Bioenergy with Carbon Capture:
Combining biomass energy with carbon capture (BECCS) can achieve net negative emissions.
Sustainable biomass sourcing is critical to ensure actual climate benefits. Land use
implications and competition with food production require careful consideration.

Natural Carbon Removal:
Nature-based solutions include afforestation, reforestation, soil carbon management,
and ocean-based approaches. These methods often provide co-benefits for biodiversity
and ecosystem services. Permanence and measurement challenges affect their role in
climate strategies."""
    },
    {
        "filename": "climate_policy_frameworks.md",
        "content": """Climate Policy and Governance Frameworks

Effective climate action requires robust policy frameworks at international, national,
and local levels. This document outlines key policy mechanisms and governance structures.

International Agreements:
The international climate regime has evolved through successive agreements establishing
emissions reduction commitments and support mechanisms. Countries submit nationally
determined contributions outlining their climate targets and actions. Regular review
processes assess collective progress and encourage increased ambition over time.
Differentiated responsibilities recognize varying national circumstances and capabilities.

Carbon Pricing Mechanisms:
Carbon pricing puts a cost on greenhouse gas emissions to incentivize reductions.
Emissions trading systems (cap-and-trade) set an overall limit and allow trading of
allowances. Carbon taxes directly price emissions, providing cost certainty. Hybrid
approaches combine elements of both. Revenue use significantly affects economic and
distributional outcomes.

Regulatory Standards:
Performance standards mandate efficiency levels or emissions limits for products,
buildings, vehicles, and industrial processes. Building codes address energy efficiency
in new construction and renovations. Vehicle standards drive improvements in fuel
economy and electrification. Industrial regulations target major emission sources.

Financial Policies:
Climate finance supports mitigation and adaptation in developing countries. Green
bonds and sustainable finance taxonomies direct private capital toward climate solutions.
Fossil fuel subsidy reform removes incentives for high-emission activities. Risk
disclosure requirements increase transparency about climate-related financial risks.

National Climate Strategies:
Comprehensive national strategies coordinate action across sectors and governance levels.
Long-term decarbonization pathways guide investment and planning decisions. Sectoral
targets address emissions from energy, transport, industry, agriculture, and buildings.
Just transition policies address social and economic impacts of the energy transition.

Subnational and Corporate Action:
Cities, states, and regions often lead with ambitious climate policies. Corporate
sustainability commitments include science-based targets and net-zero pledges.
Supply chain initiatives extend climate action through business relationships.
Voluntary standards and certification schemes complement regulatory approaches."""
    },
    {
        "filename": "climate_adaptation_resilience.md",
        "content": """Climate Adaptation and Resilience Strategies

Even with aggressive mitigation, some climate change impacts are unavoidable. Adaptation
strategies help communities, ecosystems, and economies adjust to changing conditions
and build resilience against climate risks.

Risk Assessment:
Climate risk assessment identifies vulnerabilities and potential impacts. This includes
analyzing exposure to hazards, sensitivity of systems, and adaptive capacity. Scenario
planning considers a range of possible futures. Risk assessment informs prioritization
of adaptation investments and actions.

Coastal Adaptation:
Rising sea levels and increased storm intensity threaten coastal communities and
infrastructure. Responses include protective infrastructure such as seawalls and
flood barriers. Nature-based solutions like wetland restoration provide protection
while supporting ecosystems. Managed retreat from high-risk areas may be necessary
in some locations. Building codes and land use planning reduce future exposure.

Water Resource Management:
Climate change affects water availability, quality, and demand. Integrated water
resource management balances competing uses. Infrastructure investments address
changing precipitation patterns and extreme events. Efficiency improvements reduce
demand pressure. Groundwater management ensures sustainable use of aquifers.

Agricultural Resilience:
Agriculture faces threats from changing temperature and precipitation patterns,
extreme events, and shifting pest and disease pressures. Adaptation strategies
include drought-resistant crop varieties, improved irrigation efficiency, diversified
farming systems, and adjusted planting schedules. Climate information services
support farmer decision-making.

Urban Resilience:
Cities face particular climate risks including heat waves, flooding, and infrastructure
disruption. Urban heat island mitigation includes green spaces, cool roofs, and
urban forestry. Stormwater management addresses increased precipitation intensity.
Critical infrastructure protection ensures continued essential services.

Ecosystem-Based Adaptation:
Healthy ecosystems provide natural protection against climate impacts. Forest
conservation and restoration reduce flood and landslide risks. Coral reef and
mangrove protection buffer coastal communities. Ecosystem-based approaches often
provide multiple benefits including carbon storage and biodiversity conservation.

Health System Preparedness:
Climate change affects human health through heat stress, air quality, disease
vectors, and food security. Health system adaptation includes surveillance systems,
emergency response capacity, and public health interventions. Vulnerable populations
require targeted support and protection measures."""
    },
]


def create_synthetic_documents(base_path: Path, documents: list[dict]) -> tuple[str, list[dict]]:
    """
    Create synthetic documents in the specified directory.

    Args:
        base_path: Directory to store the documents
        documents: List of document dicts with 'filename' and 'content' keys

    Returns:
        Tuple of (directory_path, list of file_path objects for SyftAI-Space)
        The file_path objects have 'path' and 'description' keys as required
        by the SyftAI-Space filePaths configuration schema.
    """
    # Ensure directory exists
    base_path.mkdir(parents=True, exist_ok=True)

    created_files = []
    for doc in documents:
        file_path = base_path / doc["filename"]
        file_path.write_text(doc["content"])
        # SyftAI-Space expects objects with 'path' and 'description' keys
        created_files.append({
            "path": str(file_path.absolute()),
            "description": doc["filename"].replace("_", " ").replace(".md", "").title()
        })

    return str(base_path.absolute()), created_files


# ============================================================================
# Weaviate Provisioner and Dataset Creation
# ============================================================================


def check_weaviate_health(weaviate_host: str, weaviate_port: int) -> bool:
    """
    Check if the external Weaviate service is healthy.

    Args:
        weaviate_host: Weaviate hostname
        weaviate_port: Weaviate HTTP port

    Returns:
        True if healthy, False otherwise
    """
    print(f"\n  Checking Weaviate health at {weaviate_host}:{weaviate_port}...")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"http://{weaviate_host}:{weaviate_port}/v1/.well-known/ready")
            if response.status_code == 200:
                print("    Weaviate is healthy!")
                return True
            else:
                print(f"    Weaviate not ready: {response.status_code}")
                return False
    except Exception as e:
        print(f"    Cannot reach Weaviate: {e}")
        return False


def create_dataset_with_documents(
    client: httpx.Client,
    headers: dict[str, str],
    dataset_name: str,
    collection_name: str,
    file_paths: list[dict],
    weaviate_host: str = "weaviate",
    weaviate_http_port: int = 8080,
    weaviate_grpc_port: int = 50051,
    retry_interval: int = 10,
    summary: str = "Documents for RAG demonstration",
    tags: str = "demo,rag",
) -> dict | None:
    """
    Create a dataset in SyftAI-Space and ingest documents.

    This function will retry indefinitely on timeout errors, as the first dataset
    creation may take a long time while SyftAI-Space downloads embedding models.

    Args:
        client: HTTPX client for SyftAI-Space
        headers: Request headers including tenant
        dataset_name: Name for the dataset
        collection_name: Weaviate collection name
        file_paths: List of file path objects with 'path' and 'description' keys
                   (matches SyftAI-Space filePaths configuration schema)
        weaviate_host: Hostname of Weaviate server (default: "weaviate" for Docker)
        weaviate_http_port: HTTP port of Weaviate server
        weaviate_grpc_port: gRPC port of Weaviate server
        retry_interval: Seconds to wait between retries on timeout (default: 10)
        summary: Dataset summary description
        tags: Comma-separated tags for the dataset

    Returns:
        Created dataset dict or None on failure
    """
    print(f"\n  Creating dataset '{dataset_name}'...")
    print(f"    Weaviate config: {weaviate_host}:{weaviate_http_port}")

    # Check if dataset already exists
    try:
        get_response = client.get(f"/api/v1/datasets/{dataset_name}", headers=headers)
        if get_response.status_code == 200:
            print(f"    Dataset '{dataset_name}' already exists")
            return get_response.json()
    except Exception:
        pass

    # Create the dataset with Weaviate connection info
    dataset_data = {
        "name": dataset_name,
        "dtype": "local_file",
        "configuration": {
            "host": weaviate_host,
            "httpPort": weaviate_http_port,
            "grpcPort": weaviate_grpc_port,
            "collectionName": collection_name,
            "ingestFileTypeOptions": [".pdf", ".md"],
            "filePaths": file_paths,
        },
        "summary": summary,
        "tags": tags,
    }

    # Retry loop for handling timeouts during embedding model download
    attempt = 0
    while True:
        attempt += 1
        try:
            if attempt == 1:
                print(f"    Sending dataset creation request...")
                print(f"    (First run may take several minutes while downloading embedding models)")
            else:
                print(f"    Retry attempt {attempt}...")

            create_response = client.post(
                "/api/v1/datasets/",
                json=dataset_data,
                headers=headers,
                timeout=120.0,  # 2 minutes per attempt
            )

            if create_response.status_code == 201:
                dataset = create_response.json()
                print(f"    Dataset created: {dataset['name']} (ID: {dataset['id']})")
                return dataset
            elif create_response.status_code == 409:
                print(f"    Dataset '{dataset_name}' already exists")
                # Try to fetch it
                get_response = client.get(f"/api/v1/datasets/{dataset_name}", headers=headers)
                if get_response.status_code == 200:
                    return get_response.json()
                return None
            else:
                print(f"    Failed to create dataset: {create_response.status_code} - {create_response.text}")
                return None

        except httpx.TimeoutException:
            print(f"    Request timed out (attempt {attempt})")
            print(f"    SyftAI-Space may be downloading embedding models...")
            print(f"    Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)
            continue

        except httpx.ConnectError as e:
            print(f"    Connection error (attempt {attempt}): {e}")
            print(f"    Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)
            continue

        except Exception as e:
            print(f"    Error creating dataset: {e}")
            return None


def ingest_documents_to_dataset(
    client: httpx.Client,
    headers: dict[str, str],
    dataset_id: str,
    dataset_name: str,
    retry_interval: int = 10,
) -> bool:
    """
    Start ingestion for a dataset using SyftAI-Space's ingestion API.

    The endpoint scans files from the dataset's filePaths configuration
    and creates ingestion jobs to process them into the vector store.

    Args:
        client: HTTPX client for SyftAI-Space
        headers: Request headers including tenant
        dataset_id: UUID of the dataset (from creation response)
        dataset_name: Name of the dataset (for logging)
        retry_interval: Seconds to wait between retries on timeout

    Returns:
        True if successful, False otherwise
    """
    print(f"\n  Starting ingestion for dataset '{dataset_name}' (ID: {dataset_id})...")
    print("    (Files will be scanned from the dataset's filePaths configuration)")

    attempt = 0
    while True:
        attempt += 1
        try:
            if attempt == 1:
                print("    Sending ingestion start request...")
                print("    (First run may take time while docling downloads models)")
            else:
                print(f"    Retry attempt {attempt}...")

            # Use the correct SyftAI-Space ingestion API endpoint
            # POST /api/v1/ingestion/datasets/{dataset_id}/start
            ingest_response = client.post(
                f"/api/v1/ingestion/datasets/{dataset_id}/start",
                headers=headers,
                timeout=300.0,  # 5 minutes for document processing
            )

            if ingest_response.status_code == 200:
                result = ingest_response.json()
                print(f"    Success: {result.get('message', 'Ingestion started')}")
                jobs_created = result.get('jobs_created', 0)
                is_watching = result.get('is_watching', False)
                print(f"    Jobs created: {jobs_created}")
                print(f"    File watcher active: {is_watching}")
                return True
            elif ingest_response.status_code == 404:
                print(f"    Dataset not found or ingestion not supported for this dataset type")
                print(f"    Response: {ingest_response.text}")
                return False
            else:
                print(f"    Ingest failed: {ingest_response.status_code} - {ingest_response.text}")
                return False

        except httpx.TimeoutException:
            print(f"    Request timed out (attempt {attempt})")
            print(f"    Docling may be downloading models or processing documents...")
            print(f"    Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)
            continue

        except httpx.ConnectError as e:
            print(f"    Connection error (attempt {attempt}): {e}")
            print(f"    Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)
            continue

        except Exception as e:
            print(f"    Error during ingestion: {e}")
            return False


def create_demo_user_data() -> dict:
    """Generate unique user registration data."""
    unique_id = generate_unique_id()
    timestamp = datetime.now().strftime("%Y%m%d")

    return {
        "username": f"demo_user_{unique_id}",
        "email": f"demo_{unique_id}@example.com",
        "password": "DemoPass123!",
        "full_name": f"Demo User {timestamp}",
    }


# ============================================================================
# SyftAI-Space Endpoint Creation
# ============================================================================


def create_syftai_space_resources(
    syftai_space_url: str, openai_api_key: str | None, docs_path: Path
) -> dict[str, dict]:
    """
    Create model instances, datasets, and endpoints in SyftAI-Space.

    Args:
        syftai_space_url: URL of the SyftAI-Space API
        openai_api_key: OpenAI API key (optional)
        docs_path: Path to store synthetic documents

    Returns a dict of created resources with their IDs and slugs.
    """
    resources = {
        "models": [],
        "datasets": [],
        "endpoints": [],
        "rag_endpoints": [],  # Endpoints with both dataset and model
    }

    # Weaviate configuration - SyftAI-Space will auto-provision Weaviate
    # when a dataset is created (uses its built-in docker-compose provisioner)
    # Default ports: HTTP 8083, gRPC 50051 (from SyftAI-Space provisioner)
    weaviate_host = os.environ.get("WEAVIATE_HOST", "localhost")
    weaviate_http_port = int(os.environ.get("WEAVIATE_HTTP_PORT", "8083"))
    weaviate_grpc_port = int(os.environ.get("WEAVIATE_GRPC_PORT", "50051"))

    print("\n" + "=" * 60)
    print("Creating SyftAI-Space Resources")
    print("=" * 60)

    print(f"\nWeaviate Configuration (auto-provisioned by SyftAI-Space):")
    print(f"  Host: {weaviate_host}")
    print(f"  HTTP Port: {weaviate_http_port}")
    print(f"  gRPC Port: {weaviate_grpc_port}")

    # Headers for SyftAI-Space API (tenant header required)
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Name": "root",
    }

    with httpx.Client(base_url=syftai_space_url, timeout=30.0) as client:
        # Check health first
        print("\nChecking SyftAI-Space health...")
        try:
            health_response = client.get("/api/v1/health")
            if health_response.status_code != 200:
                print(f"  Warning: Health check returned {health_response.status_code}")
            else:
                print("  SyftAI-Space is healthy")
        except Exception as e:
            print(f"  Error checking health: {e}")
            print("  Continuing anyway...")

        # ----------------------------------------------------------------
        # STEP 1: Create synthetic documents for all datasets
        # ----------------------------------------------------------------
        print("\n" + "-" * 40)
        print("Step 1: Creating Synthetic Documents")
        print("-" * 40)

        # Finance News Documents
        finance_docs_path = docs_path / "finance-news"
        finance_dir, finance_file_paths = create_synthetic_documents(finance_docs_path, FINANCE_NEWS_DOCUMENTS)
        print(f"\n  Finance News: Created {len(finance_file_paths)} documents in {finance_docs_path}")
        for fp in finance_file_paths:
            print(f"    - {Path(fp['path']).name}")

        # Tech Documentation
        tech_docs_path = docs_path / "tech-docs"
        tech_dir, tech_file_paths = create_synthetic_documents(tech_docs_path, TECH_DOCS_DOCUMENTS)
        print(f"\n  Tech Docs: Created {len(tech_file_paths)} documents in {tech_docs_path}")
        for fp in tech_file_paths:
            print(f"    - {Path(fp['path']).name}")

        # Climate Research Documents
        climate_docs_path = docs_path / "climate-research"
        climate_dir, climate_file_paths = create_synthetic_documents(climate_docs_path, CLIMATE_RESEARCH_DOCUMENTS)
        print(f"\n  Climate Research: Created {len(climate_file_paths)} documents in {climate_docs_path}")
        for fp in climate_file_paths:
            print(f"    - {Path(fp['path']).name}")

        # ----------------------------------------------------------------
        # STEP 2: Weaviate Auto-Provisioning Info
        # ----------------------------------------------------------------
        print("\n" + "-" * 40)
        print("Step 2: Weaviate Vector Database (Auto-Provisioned)")
        print("-" * 40)

        print("\n  SyftAI-Space will auto-provision Weaviate when the dataset is created")
        print(f"  Expected location: {weaviate_host}:{weaviate_http_port}")
        print("  Provisioner uses docker-compose to start Weaviate container")

        # ----------------------------------------------------------------
        # STEP 3: Create Datasets and Ingest Documents
        # ----------------------------------------------------------------
        print("\n" + "-" * 40)
        print("Step 3: Creating Datasets and Ingesting Documents")
        print("-" * 40)

        # Dataset 1: Finance News
        print("\n  [1/3] Finance News Dataset")
        finance_dataset = create_dataset_with_documents(
            client,
            headers,
            dataset_name="finance-news",
            collection_name="FinanceNews",
            file_paths=finance_file_paths,
            weaviate_host=weaviate_host,
            weaviate_http_port=weaviate_http_port,
            weaviate_grpc_port=weaviate_grpc_port,
            summary="Financial news and market analysis covering various sectors and economic topics",
            tags="finance,news,markets,economics,investing",
        )

        if finance_dataset:
            resources["datasets"].append(finance_dataset)
            ingest_documents_to_dataset(
                client, headers,
                dataset_id=finance_dataset["id"],
                dataset_name="finance-news"
            )
        else:
            print("    Warning: Finance News dataset creation failed")

        # Dataset 2: Tech Documentation
        print("\n  [2/3] Tech Documentation Dataset")
        tech_dataset = create_dataset_with_documents(
            client,
            headers,
            dataset_name="tech-docs",
            collection_name="TechDocs",
            file_paths=tech_file_paths,
            weaviate_host=weaviate_host,
            weaviate_http_port=weaviate_http_port,
            weaviate_grpc_port=weaviate_grpc_port,
            summary="Software engineering documentation covering development practices and architecture",
            tags="tech,docs,api,devops,architecture",
        )

        if tech_dataset:
            resources["datasets"].append(tech_dataset)
            ingest_documents_to_dataset(
                client, headers,
                dataset_id=tech_dataset["id"],
                dataset_name="tech-docs"
            )
        else:
            print("    Warning: Tech Docs dataset creation failed")

        # Dataset 3: Climate Research
        print("\n  [3/3] Climate Research Dataset")
        climate_dataset = create_dataset_with_documents(
            client,
            headers,
            dataset_name="climate-research",
            collection_name="ClimateResearch",
            file_paths=climate_file_paths,
            weaviate_host=weaviate_host,
            weaviate_http_port=weaviate_http_port,
            weaviate_grpc_port=weaviate_grpc_port,
            summary="Climate science and sustainability research covering environmental topics",
            tags="climate,research,environment,sustainability,energy",
        )

        if climate_dataset:
            resources["datasets"].append(climate_dataset)
            ingest_documents_to_dataset(
                client, headers,
                dataset_id=climate_dataset["id"],
                dataset_name="climate-research"
            )
        else:
            print("    Warning: Climate Research dataset creation failed")

        # ----------------------------------------------------------------
        # STEP 4: Create OpenAI Models (if API key provided)
        # ----------------------------------------------------------------
        print("\n" + "-" * 40)
        print("Step 4: Creating OpenAI Models")
        print("-" * 40)

        if openai_api_key:
            models_to_create = [
                {
                    "name": "gpt-4.1-mini",
                    "dtype": "openai",
                    "configuration": {
                        "api_key": openai_api_key,
                        "model": "gpt-4.1-mini",
                    },
                    "summary": "GPT-4.1 Mini - Fast and highly capable model",
                    "tags": "openai,gpt-4.1,chat,fast,capable",
                },
                {
                    "name": "gpt-4.1-nano",
                    "dtype": "openai",
                    "configuration": {
                        "api_key": openai_api_key,
                        "model": "gpt-4.1-nano",
                    },
                    "summary": "GPT-4.1 Nano - Ultra-fast and efficient model",
                    "tags": "openai,gpt-4.1,chat,efficient,fast",
                },
            ]

            print("\n  Creating OpenAI models in SyftAI-Space...")
            for model_data in models_to_create:
                try:
                    response = client.post(
                        "/api/v1/models/", json=model_data, headers=headers
                    )
                    if response.status_code == 201:
                        model = response.json()
                        resources["models"].append(model)
                        print(f"    Created model: {model['name']} (ID: {model['id']})")
                    elif response.status_code == 409 or (response.status_code == 400 and "already exists" in response.text.lower()):
                        # Model already exists, try to get it
                        print(f"    Model {model_data['name']} already exists, fetching...")
                        get_response = client.get(
                            f"/api/v1/models/{model_data['name']}", headers=headers
                        )
                        if get_response.status_code == 200:
                            model = get_response.json()
                            resources["models"].append(model)
                            print(f"    Retrieved existing model: {model['name']} (ID: {model['id']})")
                        else:
                            print(f"    Failed to get existing model: {get_response.status_code}")
                    else:
                        print(
                            f"    Failed to create model {model_data['name']}: "
                            f"{response.status_code} - {response.text}"
                        )
                except Exception as e:
                    print(f"    Error creating model {model_data['name']}: {e}")
        else:
            print("\n  Skipping model creation (no OPENAI_API_KEY provided)")
            print("    Models require an OpenAI API key to function")

        # ----------------------------------------------------------------
        # STEP 5: Create Endpoints (model-only and RAG)
        # ----------------------------------------------------------------
        print("\n" + "-" * 40)
        print("Step 5: Creating Endpoints in SyftAI-Space")
        print("-" * 40)

        # Create model-only endpoints (no dataset required)
        print("\n  Creating model-only endpoints...")
        for model in resources["models"]:
            endpoint_data = {
                "name": f"{model['name']} Chat Endpoint",
                "slug": f"{model['name'].replace('.', '-').lower()}-chat",
                "description": f"# {model['name']} Chat\n\nChat endpoint powered by {model['name']}.",
                "summary": model["summary"],
                "model_id": model["id"],
                "dataset_id": None,  # Model-only endpoint
                "response_type": "summary",  # Only LLM response, no retrieval
                "visibility": ["*"],  # Public
                "published": True,
                "tags": model["tags"],
            }

            try:
                response = client.post(
                    "/api/v1/endpoints/", json=endpoint_data, headers=headers
                )
                if response.status_code == 201:
                    endpoint = response.json()
                    resources["endpoints"].append(endpoint)
                    print(
                        f"    Created endpoint: {endpoint['name']} "
                        f"(slug: {endpoint['slug']})"
                    )
                elif response.status_code == 409 or (response.status_code == 400 and "already exists" in response.text.lower()):
                    print(f"    Endpoint {endpoint_data['slug']} already exists, fetching...")
                    get_response = client.get(
                        f"/api/v1/endpoints/{endpoint_data['slug']}", headers=headers
                    )
                    if get_response.status_code == 200:
                        endpoint = get_response.json()
                        resources["endpoints"].append(endpoint)
                        print(f"    Retrieved existing endpoint: {endpoint['name']}")
                else:
                    print(
                        f"    Failed to create endpoint {endpoint_data['slug']}: "
                        f"{response.status_code} - {response.text}"
                    )
            except Exception as e:
                print(f"    Error creating endpoint: {e}")

        # Create RAG endpoints (one per dataset, using default model)
        if resources["datasets"] and resources["models"]:
            print("\n  Creating RAG endpoints (one per dataset)...")
            default_model = resources["models"][0]  # Use gpt-4.1-mini as default

            # Define RAG endpoint configurations for each dataset
            rag_configs = [
                {
                    "dataset_name": "finance-news",
                    "endpoint_name": "Finance News",
                    "slug": "finance-news",
                    "description": """# Finance News Knowledge Base

A RAG-powered knowledge base containing financial news and market analysis articles.

## Topics Covered

- **Corporate Earnings** - Quarterly financial reports and performance analysis from major technology and other sectors
- **Monetary Policy** - Central bank decisions, interest rate policies, and economic indicators
- **Digital Assets** - Cryptocurrency market trends, institutional adoption, and regulatory developments
- **Global Markets** - International market performance, regional economic conditions, and cross-border investment flows
- **Sustainable Finance** - ESG investing trends, green bonds, and corporate sustainability initiatives

## How It Works

This endpoint uses Retrieval-Augmented Generation (RAG) to answer your questions:
1. Your question is semantically searched against the knowledge base
2. Relevant articles and passages are retrieved
3. An LLM synthesizes the information into a comprehensive answer

## Example Questions

- "What factors are driving technology sector performance?"
- "How are central banks approaching monetary policy?"
- "What trends are emerging in sustainable investing?"
- "How is institutional adoption affecting digital asset markets?"
""",
                    "summary": "Financial news and market analysis covering corporate earnings, monetary policy, and investment trends",
                    "tags": "finance,news,markets,economics,investing,rag",
                },
                {
                    "dataset_name": "tech-docs",
                    "endpoint_name": "Tech Documentation",
                    "slug": "tech-docs",
                    "description": """# Tech Documentation Knowledge Base

A RAG-powered knowledge base containing software engineering documentation and best practices.

## Topics Covered

- **API Design** - RESTful architecture principles, endpoint design patterns, and API versioning strategies
- **Authentication & Security** - Modern authentication protocols, token-based systems, and session management
- **Database Engineering** - Performance optimization, indexing strategies, and data modeling approaches
- **Distributed Systems** - Microservices patterns, service communication, and resilience strategies
- **DevOps Practices** - CI/CD pipelines, deployment strategies, and infrastructure automation

## How It Works

This endpoint uses Retrieval-Augmented Generation (RAG) to answer your questions:
1. Your question is semantically searched against the documentation
2. Relevant sections and code examples are retrieved
3. An LLM synthesizes the information into a comprehensive answer

## Example Questions

- "What are the recommended practices for designing REST APIs?"
- "How should authentication be implemented in modern applications?"
- "What strategies help optimize database performance?"
- "How do microservices handle failures gracefully?"
""",
                    "summary": "Software engineering documentation covering API design, security, databases, and DevOps",
                    "tags": "tech,docs,api,devops,architecture,rag",
                },
                {
                    "dataset_name": "climate-research",
                    "endpoint_name": "Climate Research",
                    "slug": "climate-research",
                    "description": """# Climate Research Knowledge Base

A RAG-powered knowledge base containing climate science and sustainability research documentation.

## Topics Covered

- **Climate Science** - Fundamental concepts including greenhouse effect, carbon cycle, and climate modeling
- **Renewable Energy** - Solar, wind, hydroelectric, geothermal technologies and grid integration
- **Carbon Management** - Capture technologies, storage solutions, and carbon removal approaches
- **Policy & Governance** - International agreements, carbon pricing mechanisms, and regulatory frameworks
- **Adaptation Strategies** - Risk assessment, resilience planning, and ecosystem-based approaches

## How It Works

This endpoint uses Retrieval-Augmented Generation (RAG) to answer your questions:
1. Your question is semantically searched against the research documentation
2. Relevant scientific content and policy information are retrieved
3. An LLM synthesizes the information into a comprehensive answer

## Example Questions

- "What are the main drivers of climate change?"
- "How do different renewable energy technologies compare?"
- "What approaches exist for carbon capture and storage?"
- "How are communities adapting to climate impacts?"
""",
                    "summary": "Climate science and sustainability research covering energy, policy, and adaptation",
                    "tags": "climate,research,environment,sustainability,energy,rag",
                },
            ]

            for config in rag_configs:
                # Find the matching dataset
                dataset = next(
                    (d for d in resources["datasets"] if d["name"] == config["dataset_name"]),
                    None
                )
                if not dataset:
                    print(f"    Skipping {config['endpoint_name']}: dataset not found")
                    continue

                rag_endpoint_data = {
                    "name": config["endpoint_name"],
                    "slug": config["slug"],
                    "description": config["description"],
                    "summary": config["summary"],
                    "model_id": default_model["id"],
                    "dataset_id": dataset["id"],
                    "response_type": "both",  # RAG mode: retrieval + generation
                    "visibility": ["*"],  # Public
                    "published": True,
                    "tags": config["tags"],
                }

                try:
                    response = client.post(
                        "/api/v1/endpoints/", json=rag_endpoint_data, headers=headers
                    )
                    if response.status_code == 201:
                        endpoint = response.json()
                        resources["rag_endpoints"].append(endpoint)
                        print(
                            f"    Created RAG endpoint: {endpoint['name']} "
                            f"(slug: {endpoint['slug']})"
                        )
                    elif response.status_code == 409 or (response.status_code == 400 and "already exists" in response.text.lower()):
                        print(f"    RAG Endpoint {rag_endpoint_data['slug']} already exists, fetching...")
                        get_response = client.get(
                            f"/api/v1/endpoints/{rag_endpoint_data['slug']}", headers=headers
                        )
                        if get_response.status_code == 200:
                            endpoint = get_response.json()
                            resources["rag_endpoints"].append(endpoint)
                            print(f"    Retrieved existing RAG endpoint: {endpoint['name']}")
                    else:
                        print(
                            f"    Failed to create RAG endpoint: "
                            f"{response.status_code} - {response.text}"
                        )
                except Exception as e:
                    print(f"    Error creating RAG endpoint: {e}")
        else:
            print("\n  Skipping RAG endpoint creation (missing dataset or model)")

    print(f"\n" + "-" * 40)
    print("SyftAI-Space Resources Summary:")
    print("-" * 40)
    print(f"  Datasets: {len(resources['datasets'])}")
    print(f"  Models: {len(resources['models'])}")
    print(f"  Model-only Endpoints: {len(resources['endpoints'])}")
    print(f"  RAG Endpoints: {len(resources['rag_endpoints'])}")

    return resources


# ============================================================================
# SyftHub Endpoint Registration
# ============================================================================


def get_syfthub_endpoints(
    syftai_space_url: str, syftai_resources: dict[str, dict]
) -> tuple[list[dict], list[dict]]:
    """
    Generate SyftHub endpoint definitions based on SyftAI-Space resources.

    Returns (data_source_endpoints, model_endpoints) lists.
    """
    # The URL that the aggregator (running in Docker) uses to reach SyftAI-Space (on host)
    # Uses host.docker.internal to access the host machine from inside Docker containers
    syftai_internal_url = os.environ.get(
        "SYFTAI_SPACE_INTERNAL_URL", "http://host.docker.internal:8085"
    )

    data_source_endpoints = []
    model_endpoints = []

    # ----------------------------------------------------------------
    # Register Model-Only Endpoints in SyftHub
    # ----------------------------------------------------------------
    for endpoint in syftai_resources.get("endpoints", []):
        # Determine policies based on model type
        is_mini = "mini" in endpoint["slug"]

        if is_mini:
            # gpt-4.1-mini: Premium model with rate limiting and access control
            model_policies = [
                Policy(
                    type="transaction",
                    version="1.0",
                    enabled=True,
                    description="Token-based transaction costs for model inference",
                    config={
                        "provider": "SyftAI-Space",
                        "pricing_model": "per_token",
                        "costs": {
                            "input_tokens": 0.0000004,
                            "output_tokens": 0.0000016,
                            "currency": "USD",
                        },
                        "billing_unit": "token",
                    },
                ),
                Policy(
                    type="rate_limit",
                    version="1.0",
                    enabled=True,
                    description="Request rate limiting to prevent abuse",
                    config={
                        "limit": "50/m",  # 50 requests per minute (stricter for premium)
                        "scope": "per_user",
                        "applied_to": ["*"],
                    },
                ),
                Policy(
                    type="access_control",
                    version="1.0",
                    enabled=True,
                    description="Concurrent user access limits",
                    config={
                        "max_concurrent_users": 5,
                        "queue_enabled": True,
                        "queue_timeout_seconds": 30,
                    },
                ),
            ]
        else:
            # gpt-4.1-nano: Free tier with usage rights restrictions
            model_policies = [
                Policy(
                    type="transaction",
                    version="1.0",
                    enabled=True,
                    description="Token-based transaction costs for model inference",
                    config={
                        "provider": "SyftAI-Space",
                        "pricing_model": "per_token",
                        "costs": {
                            "input_tokens": 0.0000001,
                            "output_tokens": 0.0000004,
                            "currency": "USD",
                        },
                        "billing_unit": "token",
                    },
                ),
                Policy(
                    type="usage-rights",
                    version="1.0",
                    enabled=True,
                    description="Permitted usage scenarios for free tier",
                    config={
                        "allowed_purposes": ["academic", "research", "personal"],
                        "attribution_required": True,
                        "redistribution_allowed": False,
                        "modification_allowed": False,
                        "commercial_use": False,
                    },
                ),
            ]

        model_endpoint = {
            "name": endpoint["name"],
            "type": EndpointType.MODEL,
            "visibility": Visibility.PUBLIC,
            "slug": endpoint["slug"],  # Same slug as in SyftAI-Space!
            "description": endpoint.get("summary", "SyftAI-Space model endpoint"),
            "version": "1.0.0",
            "readme": f"""# {endpoint['name']}

## Overview
This endpoint is powered by SyftAI-Space and provides LLM chat capabilities.

## Connection
- **SyftAI-Space URL**: `{syftai_internal_url}`
- **Endpoint Slug**: `{endpoint['slug']}`

## Usage
Select this model in the SyftHub chat interface to use it for conversations.
The aggregator will route requests to the SyftAI-Space endpoint.

## API
Query endpoint: `POST {syftai_internal_url}/api/v1/endpoints/{endpoint['slug']}/query`
""",
            "policies": model_policies,
            "connect": [
                Connection(
                    type="syftai_space",
                    enabled=True,
                    description="SyftAI-Space model endpoint",
                    config={
                        "url": syftai_internal_url,
                        "tenant_name": "root",  # Required for SyftAI-Space multi-tenancy
                    },
                ),
            ],
        }
        model_endpoints.append(model_endpoint)

    # ----------------------------------------------------------------
    # Register RAG Endpoints as Data Sources in SyftHub
    # These endpoints have BOTH dataset and model, enabling RAG queries
    # Clean names without model references - data sources represent knowledge bases
    # ----------------------------------------------------------------
    # Define readme templates for each data source type
    readme_templates = {
        "finance-news": """# Finance News Knowledge Base

## Overview

A **RAG (Retrieval-Augmented Generation)** powered knowledge base containing financial news and market analysis articles.

## Topics Covered

| Category | Description |
|----------|-------------|
| **Corporate Earnings** | Quarterly financial reports and performance analysis across major sectors |
| **Monetary Policy** | Central bank decisions, interest rate policies, and economic indicators |
| **Digital Assets** | Cryptocurrency market trends, institutional developments, and regulations |
| **Global Markets** | International market performance and regional economic conditions |
| **Sustainable Finance** | ESG investing trends, green bonds, and sustainability initiatives |

## How It Works

This knowledge base uses semantic search to find relevant information:

1. **Search** - Your question is converted to embeddings and matched against the document collection
2. **Retrieve** - The most relevant passages and articles are retrieved
3. **Generate** - An LLM synthesizes the information into a comprehensive answer

## Example Questions

- "What factors influence corporate earnings in the technology sector?"
- "How do central banks communicate monetary policy decisions?"
- "What role does institutional investment play in digital asset markets?"
- "What are the key trends in sustainable and ESG investing?"
""",
        "tech-docs": """# Tech Documentation Knowledge Base

## Overview

A **RAG (Retrieval-Augmented Generation)** powered knowledge base containing software engineering documentation and best practices.

## Topics Covered

| Category | Description |
|----------|-------------|
| **API Design** | RESTful architecture principles, endpoint patterns, and versioning strategies |
| **Authentication** | Modern auth protocols, token-based systems, and session management |
| **Database Engineering** | Performance optimization, indexing strategies, and data modeling |
| **Distributed Systems** | Microservices patterns, service communication, and resilience |
| **DevOps Practices** | CI/CD pipelines, deployment strategies, and infrastructure automation |

## How It Works

This knowledge base uses semantic search to find relevant information:

1. **Search** - Your question is converted to embeddings and matched against the documentation
2. **Retrieve** - The most relevant sections and code examples are retrieved
3. **Generate** - An LLM synthesizes the information into a comprehensive answer

## Example Questions

- "What principles should guide RESTful API design?"
- "How do modern authentication systems manage user sessions?"
- "What strategies improve database query performance?"
- "How do distributed systems handle service failures?"
""",
        "climate-research": """# Climate Research Knowledge Base

## Overview

A **RAG (Retrieval-Augmented Generation)** powered knowledge base containing climate science and sustainability research documentation.

## Topics Covered

| Category | Description |
|----------|-------------|
| **Climate Science** | Fundamental concepts including greenhouse effect, carbon cycle, and climate modeling |
| **Renewable Energy** | Solar, wind, hydroelectric, and geothermal technologies |
| **Carbon Management** | Capture technologies, storage solutions, and removal approaches |
| **Policy & Governance** | International agreements, carbon pricing, and regulatory frameworks |
| **Adaptation Strategies** | Risk assessment, resilience planning, and ecosystem-based approaches |

## How It Works

This knowledge base uses semantic search to find relevant information:

1. **Search** - Your question is converted to embeddings and matched against the research documentation
2. **Retrieve** - The most relevant scientific content and policy information are retrieved
3. **Generate** - An LLM synthesizes the information into a comprehensive answer

## Example Questions

- "What are the fundamental mechanisms driving climate change?"
- "How do different renewable energy sources compare in terms of efficiency?"
- "What technologies exist for capturing and storing carbon?"
- "How are communities building resilience to climate impacts?"
""",
    }

    for rag_endpoint in syftai_resources.get("rag_endpoints", []):
        slug = rag_endpoint["slug"]
        readme = readme_templates.get(slug, f"# {rag_endpoint['name']}\n\nRAG-powered knowledge base.")

        # Determine policies based on data source type
        if slug == "finance-news":
            # Finance News: Strict compliance with data retention and privacy
            data_source_policies = [
                Policy(
                    type="transaction",
                    version="1.0",
                    enabled=True,
                    description="Token-based transaction costs for RAG queries",
                    config={
                        "provider": "SyftAI-Space",
                        "pricing_model": "per_token",
                        "costs": {
                            "input_tokens": 0.0000005,
                            "output_tokens": 0.0000020,
                            "currency": "USD",
                        },
                        "billing_unit": "token",
                    },
                ),
                Policy(
                    type="data_retention",
                    version="1.0",
                    enabled=True,
                    description="Data retention and cleanup policy for financial data",
                    config={
                        "retention_days": 365,
                        "auto_cleanup": True,
                        "archive_before_delete": True,
                        "compliance_standard": "SOX",
                    },
                ),
                Policy(
                    type="data-privacy",
                    version="1.0",
                    enabled=True,
                    description="GDPR compliant data handling for financial information",
                    config={
                        "gdpr_compliant": True,
                        "anonymization_enabled": True,
                        "pii_detection": True,
                        "data_encryption": "AES-256",
                        "audit_logging": True,
                    },
                ),
            ]
        elif slug == "tech-docs":
            # Tech Docs: Open documentation with rate limiting and usage rights
            data_source_policies = [
                Policy(
                    type="transaction",
                    version="1.0",
                    enabled=True,
                    description="Token-based transaction costs for RAG queries",
                    config={
                        "provider": "SyftAI-Space",
                        "pricing_model": "per_token",
                        "costs": {
                            "input_tokens": 0.0000005,
                            "output_tokens": 0.0000020,
                            "currency": "USD",
                        },
                        "billing_unit": "token",
                    },
                ),
                Policy(
                    type="rate_limit",
                    version="1.0",
                    enabled=True,
                    description="Generous rate limiting for documentation access",
                    config={
                        "limit": "100/m",  # 100 requests per minute (generous for docs)
                        "scope": "per_user",
                        "applied_to": ["*"],
                    },
                ),
                Policy(
                    type="usage-rights",
                    version="1.0",
                    enabled=True,
                    description="Open usage rights for technical documentation",
                    config={
                        "allowed_purposes": ["academic", "research", "commercial", "personal"],
                        "attribution_required": True,
                        "redistribution_allowed": True,
                        "modification_allowed": True,
                        "commercial_use": True,
                    },
                ),
            ]
        elif slug == "climate-research":
            # Climate Research: Research collaboration with data retention and access control
            data_source_policies = [
                Policy(
                    type="transaction",
                    version="1.0",
                    enabled=True,
                    description="Token-based transaction costs for RAG queries",
                    config={
                        "provider": "SyftAI-Space",
                        "pricing_model": "per_token",
                        "costs": {
                            "input_tokens": 0.0000005,
                            "output_tokens": 0.0000020,
                            "currency": "USD",
                        },
                        "billing_unit": "token",
                    },
                ),
                Policy(
                    type="data_retention",
                    version="1.0",
                    enabled=True,
                    description="Extended data retention for research data",
                    config={
                        "retention_days": 730,  # 2 years for research purposes
                        "auto_cleanup": False,
                        "archive_before_delete": True,
                        "research_data_policy": True,
                    },
                ),
                Policy(
                    type="access_control",
                    version="1.0",
                    enabled=True,
                    description="Team collaboration access controls",
                    config={
                        "max_concurrent_users": 25,
                        "queue_enabled": True,
                        "queue_timeout_seconds": 60,
                        "collaboration_mode": True,
                    },
                ),
            ]
        else:
            # Default: Just transaction policy
            data_source_policies = [
                Policy(
                    type="transaction",
                    version="1.0",
                    enabled=True,
                    description="Token-based transaction costs for RAG queries",
                    config={
                        "provider": "SyftAI-Space",
                        "pricing_model": "per_token",
                        "costs": {
                            "input_tokens": 0.0000005,
                            "output_tokens": 0.0000020,
                            "currency": "USD",
                        },
                        "billing_unit": "token",
                    },
                ),
            ]

        data_source = {
            "name": rag_endpoint["name"],
            "type": EndpointType.DATA_SOURCE,
            "visibility": Visibility.PUBLIC,
            "slug": slug,  # Same slug as in SyftAI-Space!
            "description": rag_endpoint.get("summary", "SyftAI-Space RAG endpoint"),
            "version": "1.0.0",
            "readme": readme,
            "policies": data_source_policies,
            "connect": [
                Connection(
                    type="syftai_space",
                    enabled=True,
                    description="SyftAI-Space RAG endpoint",
                    config={
                        "url": syftai_internal_url,
                        "tenant_name": "root",  # Required for SyftAI-Space multi-tenancy
                    },
                ),
            ],
        }
        data_source_endpoints.append(data_source)

    # ----------------------------------------------------------------
    # Fallback: Create placeholder endpoints if nothing was created
    # ----------------------------------------------------------------
    if not model_endpoints:
        print("\nNo SyftAI-Space model endpoints available, creating placeholder...")
        model_endpoints = [
            {
                "name": "GPT-4.1 Mini Chat (Placeholder)",
                "type": EndpointType.MODEL,
                "visibility": Visibility.PUBLIC,
                "slug": "gpt-4-1-mini-chat",
                "description": "Placeholder - requires OPENAI_API_KEY and SyftAI-Space setup",
                "version": "1.0.0",
                "readme": """# GPT-4.1 Mini Chat Placeholder

This is a placeholder endpoint. To make it functional:
1. Set OPENAI_API_KEY environment variable
2. Re-run the demo script to create the model in SyftAI-Space
""",
                "policies": [
                    Policy(
                        type="transaction",
                        version="1.0",
                        enabled=True,
                        description="Token-based transaction costs (placeholder)",
                        config={
                            "provider": "SyftAI-Space",
                            "pricing_model": "per_token",
                            "costs": {
                                "input_tokens": 0.0000004,
                                "output_tokens": 0.0000016,
                                "currency": "USD",
                            },
                            "billing_unit": "token",
                            "status": "placeholder",
                        },
                    ),
                ],
                "connect": [
                    Connection(
                        type="syftai_space",
                        enabled=True,
                        description="SyftAI-Space endpoint (requires setup)",
                        config={
                            "url": syftai_internal_url,
                            "tenant_name": "root",
                        },
                    ),
                ],
            },
        ]

    if not data_source_endpoints:
        print("\nNo SyftAI-Space RAG endpoints available, creating placeholder...")
        data_source_endpoints = [
            {
                "name": "Finance News (Placeholder)",
                "type": EndpointType.DATA_SOURCE,
                "visibility": Visibility.PUBLIC,
                "slug": "finance-news-placeholder",
                "description": "Placeholder - requires Weaviate and dataset setup",
                "version": "1.0.0",
                "readme": """# Finance News Placeholder

This is a placeholder data source endpoint. To make it functional:
1. Ensure Weaviate provisioner is running
2. Create a dataset with documents
3. Create an endpoint with dataset_id + model_id
4. Re-run the demo script
""",
                "policies": [
                    Policy(
                        type="transaction",
                        version="1.0",
                        enabled=True,
                        description="Token-based transaction costs (placeholder)",
                        config={
                            "provider": "SyftAI-Space",
                            "pricing_model": "per_token",
                            "costs": {
                                "input_tokens": 0.0000005,
                                "output_tokens": 0.0000020,
                                "currency": "USD",
                            },
                            "billing_unit": "token",
                            "status": "placeholder",
                        },
                    ),
                ],
                "connect": [
                    Connection(
                        type="syftai_space",
                        enabled=True,
                        description="SyftAI-Space data source (requires setup)",
                        config={
                            "url": syftai_internal_url,
                            "tenant_name": "root",
                        },
                    ),
                ],
            },
        ]

    return data_source_endpoints, model_endpoints


def main() -> int:
    """Main function to run the full stack demo."""
    print("=" * 60)
    print("SyftHub Full Stack Demo: SyftAI-Space + SyftHub Integration")
    print("=" * 60)

    # Get configuration from environment
    syfthub_url = os.environ.get("SYFTHUB_URL", "http://localhost:8080")
    # SyftAI-Space runs locally on host at port 8085 (not in Docker)
    syftai_space_url = os.environ.get("SYFTAI_SPACE_URL", "http://localhost:8085")
    openai_api_key = os.environ.get("OPENAI_API_KEY")

    # Path for synthetic documents
    # Since SyftAI-Space runs locally, it can access local filesystem paths
    docs_path = Path(os.environ.get("DEMO_DOCS_PATH", "/tmp/syfthub-demo-docs"))

    print(f"\nConfiguration:")
    print(f"  SyftHub URL: {syfthub_url}")
    print(f"  SyftAI-Space URL: {syftai_space_url}")
    print(f"  OpenAI API Key: {'***' + openai_api_key[-4:] if openai_api_key else 'Not set'}")
    print(f"  Documents Path: {docs_path}")

    if not openai_api_key:
        print("\nWarning: OPENAI_API_KEY not set")
        print("  Model endpoints will be created but won't function without an API key")

    # Generate unique user data
    user_data = create_demo_user_data()
    print("\nGenerated demo user:")
    print(f"  Username: {user_data['username']}")
    print(f"  Email: {user_data['email']}")
    print(f"  Full Name: {user_data['full_name']}")

    try:
        # ----------------------------------------------------------------
        # PART 1: Create resources in SyftAI-Space
        # ----------------------------------------------------------------
        syftai_resources = create_syftai_space_resources(
            syftai_space_url, openai_api_key, docs_path
        )

        # ----------------------------------------------------------------
        # PART 2: Register endpoints in SyftHub
        # ----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("Registering Endpoints in SyftHub")
        print("=" * 60)

        # Create SyftHub client
        print("\nCreating SyftHub client...")
        client = SyftHubClient(base_url=syfthub_url)
        print("  Client created successfully")

        # Register user
        print("\nRegistering new user in SyftHub...")
        user = client.auth.register(
            username=user_data["username"],
            email=user_data["email"],
            password=user_data["password"],
            full_name=user_data["full_name"],
        )
        print(f"  User registered: {user.username} (ID: {user.id})")

        # Login
        print("\nLogging in...")
        user = client.auth.login(
            username=user_data["username"],
            password=user_data["password"],
        )
        print(f"  Logged in as: {user.username}")

        # Get endpoint definitions
        data_source_endpoints, model_endpoints = get_syfthub_endpoints(
            syftai_space_url, syftai_resources
        )

        # Create model endpoints
        print("\nCreating model endpoints in SyftHub...")
        created_models = []
        for i, endpoint_data in enumerate(model_endpoints, 1):
            try:
                endpoint = client.my_endpoints.create(**endpoint_data)
                created_models.append(endpoint)
                print(f"  [{i}/{len(model_endpoints)}] Created: {endpoint.name}")
                print(f"      Slug: {endpoint.slug}")
                print(f"      Type: {endpoint.type}")
            except Exception as e:
                print(f"  [{i}/{len(model_endpoints)}] Failed: {endpoint_data['name']}")
                print(f"      Error: {e}")

        # Create data source endpoints
        print("\nCreating data source endpoints in SyftHub...")
        created_data_sources = []
        for i, endpoint_data in enumerate(data_source_endpoints, 1):
            try:
                endpoint = client.my_endpoints.create(**endpoint_data)
                created_data_sources.append(endpoint)
                print(f"  [{i}/{len(data_source_endpoints)}] Created: {endpoint.name}")
                print(f"      Slug: {endpoint.slug}")
                print(f"      Type: {endpoint.type}")
            except Exception as e:
                print(f"  [{i}/{len(data_source_endpoints)}] Failed: {endpoint_data['name']}")
                print(f"      Error: {e}")

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        print("\nUser Created:")
        print(f"  Username: {user_data['username']}")
        print(f"  Password: {user_data['password']}")
        print(f"  Email: {user_data['email']}")

        print(f"\nSyftAI-Space Resources:")
        print(f"  Datasets: {len(syftai_resources.get('datasets', []))}")
        for ds in syftai_resources.get("datasets", []):
            print(f"    - {ds['name']} (ID: {ds['id']})")
        print(f"  Models: {len(syftai_resources.get('models', []))}")
        for m in syftai_resources.get("models", []):
            print(f"    - {m['name']} (ID: {m['id']})")
        print(f"  Model-only Endpoints: {len(syftai_resources.get('endpoints', []))}")
        print(f"  RAG Endpoints: {len(syftai_resources.get('rag_endpoints', []))}")
        for ep in syftai_resources.get("rag_endpoints", []):
            print(f"    - {ep['name']} (slug: {ep['slug']})")

        print(f"\nSyftHub Endpoints:")
        print(f"  Model Endpoints: {len(created_models)}")
        for ep in created_models:
            print(f"    - {ep.name} -> {user_data['username']}/{ep.slug}")
        print(f"  Data Source Endpoints (RAG): {len(created_data_sources)}")
        for ep in created_data_sources:
            print(f"    - {ep.name} -> {user_data['username']}/{ep.slug}")

        print("\n" + "-" * 60)
        print("Next Steps:")
        print("-" * 60)
        print("1. Open http://localhost:8080 in your browser")
        print(f"2. Login with username '{user_data['username']}' and password '{user_data['password']}'")
        print("3. Navigate to the Chat section")
        print("4. Select a model (GPT-4.1 Mini or GPT-4.1 Nano)")
        print("5. Select a data source (Finance News, Tech Documentation, or Climate Research)")
        print("6. Ask questions to query the knowledge bases!")
        print("\nExample questions for Finance News:")
        print("  - 'What factors are driving technology sector earnings?'")
        print("  - 'How are central banks approaching monetary policy?'")
        print("  - 'What trends are emerging in sustainable investing?'")
        print("\nExample questions for Tech Documentation:")
        print("  - 'What principles guide RESTful API design?'")
        print("  - 'How do modern authentication systems work?'")
        print("  - 'What patterns help distributed systems handle failures?'")
        print("\nExample questions for Climate Research:")
        print("  - 'What are the main drivers of climate change?'")
        print("  - 'How do renewable energy technologies compare?'")
        print("  - 'What approaches exist for carbon capture and storage?'")
        print("\nNote: The aggregator will call SyftAI-Space endpoints using the")
        print("      URL and slug registered in SyftHub.")
        print("\nDemo completed successfully!")

        # Cleanup
        client.close()
        return 0

    except AuthenticationError as e:
        print(f"\nAuthentication Error: {e}")
        return 1
    except ValidationError as e:
        print(f"\nValidation Error: {e}")
        return 1
    except SyftHubError as e:
        print(f"\nSyftHub Error: {e}")
        return 1
    except httpx.ConnectError as e:
        print(f"\nConnection Error: {e}")
        print("Make sure the services are running:")
        print("  docker compose -f docker-compose.fullstack.yml up")
        return 1
    except Exception as e:
        print(f"\nUnexpected Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
