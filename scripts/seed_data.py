#!/usr/bin/env python3
"""
Seed script to populate Syfthub with sample data.

This script creates:
- 15 diverse users with realistic profiles
- 8 organizations across different domains
- 35+ datasites with various configurations
- Organization memberships and datasite ownership

Run this script after starting the Syfthub server to populate it with test data.
"""

import asyncio

import httpx


class SyfthubSeeder:
    """Seeder client for populating Syfthub with sample data."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize seeder with API base URL."""
        self.base_url = base_url
        self.api_url = f"{base_url}/api/v1"
        self.users = {}  # username -> user_data
        self.organizations = {}  # slug -> org_data
        self.auth_tokens = {}  # username -> token

    async def seed_all(self) -> None:
        """Run complete data seeding process."""
        print(f"🌱 Starting data seeding for Syfthub at {self.base_url}")

        async with httpx.AsyncClient() as client:
            await self._check_server_health(client)
            await self._seed_users(client)
            await self._seed_organizations(client)
            await self._seed_datasites(client)

        print("✅ Data seeding completed successfully!")
        print(
            f"📊 Created: {len(self.users)} users, {len(self.organizations)} organizations"
        )

    async def _check_server_health(self, client: httpx.AsyncClient) -> None:
        """Check if Syfthub server is running."""
        try:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            print("✅ Syfthub server is running")
        except httpx.RequestError as e:
            print(f"❌ Cannot connect to Syfthub server: {e}")
            raise
        except httpx.HTTPStatusError as e:
            print(f"❌ Server health check failed: {e.response.status_code}")
            raise

    async def _seed_users(self, client: httpx.AsyncClient) -> None:
        """Create diverse user accounts."""
        print("👥 Creating users...")

        user_profiles = [
            # Tech professionals
            {
                "username": "alice_chen",
                "email": "alice.chen@techcorp.com",
                "full_name": "Alice Chen",
                "age": 32,
                "password": "DataScience123!",
            },
            {
                "username": "bob_smith",
                "email": "bob.smith@datalab.org",
                "full_name": "Bob Smith",
                "age": 28,
                "password": "MachineLearning456!",
            },
            {
                "username": "carol_rodriguez",
                "email": "carol@bioinformatics.edu",
                "full_name": "Carol Rodriguez",
                "age": 35,
                "password": "Genomics789!",
            },
            # Researchers
            {
                "username": "david_kim",
                "email": "d.kim@university.edu",
                "full_name": "David Kim",
                "age": 29,
                "password": "Research123!",
            },
            {
                "username": "emma_jones",
                "email": "emma.jones@climate.org",
                "full_name": "Emma Jones",
                "age": 31,
                "password": "ClimateData456!",
            },
            {
                "username": "frank_taylor",
                "email": "frank.taylor@finance.com",
                "full_name": "Frank Taylor",
                "age": 27,
                "password": "FinanceML789!",
            },
            # Academic users
            {
                "username": "grace_wang",
                "email": "grace@nlp.stanford.edu",
                "full_name": "Grace Wang",
                "age": 26,
                "password": "NaturalLanguage123!",
            },
            {
                "username": "henry_brown",
                "email": "h.brown@physics.mit.edu",
                "full_name": "Henry Brown",
                "age": 34,
                "password": "QuantumData456!",
            },
            # Industry professionals
            {
                "username": "iris_zhang",
                "email": "iris.zhang@healthcare.ai",
                "full_name": "Iris Zhang",
                "age": 30,
                "password": "HealthAI789!",
            },
            {
                "username": "jack_wilson",
                "email": "jack@robotics.tech",
                "full_name": "Jack Wilson",
                "age": 33,
                "password": "RoboticsData123!",
            },
            # Data scientists
            {
                "username": "kate_miller",
                "email": "kate.miller@ecommerce.com",
                "full_name": "Kate Miller",
                "age": 29,
                "password": "EcommerceDS456!",
            },
            {
                "username": "leo_garcia",
                "email": "leo@socialmedia.ai",
                "full_name": "Leo Garcia",
                "age": 25,
                "password": "SocialData789!",
            },
            # Additional specialists
            {
                "username": "maya_patel",
                "email": "maya.patel@automotive.tech",
                "full_name": "Maya Patel",
                "age": 28,
                "password": "AutonomousVehicles123!",
            },
            {
                "username": "noah_lee",
                "email": "noah@energy.gov",
                "full_name": "Noah Lee",
                "age": 36,
                "password": "EnergyData456!",
            },
            {
                "username": "olivia_davis",
                "email": "olivia.davis@cybersecurity.com",
                "full_name": "Olivia Davis",
                "age": 32,
                "password": "CyberThreatIntel789!",
            },
        ]

        for profile in user_profiles:
            await self._register_user(client, profile)

        print(f"✅ Created {len(user_profiles)} users")

    async def _register_user(self, client: httpx.AsyncClient, profile: dict) -> None:
        """Register a single user and store auth token."""
        try:
            response = await client.post(f"{self.api_url}/auth/register", json=profile)
            response.raise_for_status()

            data = response.json()
            username = profile["username"]

            self.users[username] = data["user"]
            self.auth_tokens[username] = data["access_token"]

            print(f"  ✅ Registered user: {username}")

        except httpx.HTTPStatusError as e:
            print(f"  ❌ Failed to register {profile['username']}: {e.response.text}")
            raise

    async def _seed_organizations(self, client: httpx.AsyncClient) -> None:
        """Create diverse organizations."""
        print("🏢 Creating organizations...")

        org_configs = [
            {
                "name": "Tech Innovation Lab",
                "slug": "tech-innovation-lab",
                "description": "Cutting-edge technology research and development",
                "avatar_url": "https://images.unsplash.com/photo-1518186285589-2f7649de83e0?w=200",
                "owner": "alice_chen",
                "members": ["bob_smith", "grace_wang"],
            },
            {
                "name": "BioDataCorp",
                "slug": "biodatacorp",
                "description": "Bioinformatics and genomics data solutions",
                "avatar_url": "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=200",
                "owner": "carol_rodriguez",
                "members": ["iris_zhang", "david_kim"],
            },
            {
                "name": "Climate Analytics",
                "slug": "climate-analytics",
                "description": "Environmental data analysis and climate modeling",
                "avatar_url": "https://images.unsplash.com/photo-1569163139342-de1c8d4d68e8?w=200",
                "owner": "emma_jones",
                "members": ["noah_lee", "henry_brown"],
            },
            {
                "name": "FinTech Data Solutions",
                "slug": "fintech-data",
                "description": "Financial technology and risk analytics",
                "avatar_url": "https://images.unsplash.com/photo-1560472354-b33ff0c44a43?w=200",
                "owner": "frank_taylor",
                "members": ["kate_miller", "leo_garcia"],
            },
            {
                "name": "AI Research Collective",
                "slug": "ai-research-collective",
                "description": "Collaborative artificial intelligence research",
                "avatar_url": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=200",
                "owner": "grace_wang",
                "members": ["alice_chen", "jack_wilson", "maya_patel"],
            },
            {
                "name": "Healthcare Intelligence",
                "slug": "healthcare-intel",
                "description": "Medical data analytics and health informatics",
                "avatar_url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?w=200",
                "owner": "iris_zhang",
                "members": ["carol_rodriguez"],
            },
            {
                "name": "Automotive Data Labs",
                "slug": "automotive-data-labs",
                "description": "Connected vehicle and autonomous driving data",
                "avatar_url": "https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=200",
                "owner": "maya_patel",
                "members": ["jack_wilson", "olivia_davis"],
            },
            {
                "name": "Open Science Foundation",
                "slug": "open-science-foundation",
                "description": "Promoting open access to scientific data",
                "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200",
                "owner": "david_kim",
                "members": ["henry_brown", "emma_jones", "noah_lee"],
            },
        ]

        for config in org_configs:
            await self._create_organization(client, config)

        print(f"✅ Created {len(org_configs)} organizations with memberships")

    async def _create_organization(
        self, client: httpx.AsyncClient, config: dict
    ) -> None:
        """Create organization and manage memberships."""
        owner = config["owner"]
        headers = {"Authorization": f"Bearer {self.auth_tokens[owner]}"}

        # Create organization
        org_data = {
            "name": config["name"],
            "slug": config["slug"],
            "description": config["description"],
            "avatar_url": config["avatar_url"],
        }

        try:
            response = await client.post(
                f"{self.api_url}/organizations/", json=org_data, headers=headers
            )
            response.raise_for_status()

            org = response.json()
            self.organizations[config["slug"]] = org

            print(f"  ✅ Created organization: {config['name']}")

            # Add members
            for member_username in config["members"]:
                await self._add_org_member(client, org["id"], member_username, headers)

        except httpx.HTTPStatusError as e:
            print(f"  ❌ Failed to create {config['name']}: {e.response.text}")
            raise

    async def _add_org_member(
        self, client: httpx.AsyncClient, org_id: int, username: str, headers: dict
    ) -> None:
        """Add member to organization."""
        try:
            user_id = self.users[username]["id"]
            member_data = {"user_id": user_id, "role": "member"}

            response = await client.post(
                f"{self.api_url}/organizations/{org_id}/members",
                json=member_data,
                headers=headers,
            )
            response.raise_for_status()

            print(f"    + Added member: {username}")

        except httpx.HTTPStatusError as e:
            print(f"    ❌ Failed to add member {username}: {e.response.text}")

    async def _seed_datasites(self, client: httpx.AsyncClient) -> None:
        """Create diverse datasites for users and organizations."""
        print("📊 Creating datasites...")

        # User-owned datasites
        user_datasets = [
            # Alice Chen - Data Science
            {
                "owner": "alice_chen",
                "type": "user",
                "name": "Customer Segmentation Dataset",
                "slug": "customer-segmentation",
                "description": "Comprehensive e-commerce customer behavior and segmentation data",
                "visibility": "public",
                "version": "2.1.0",
                "stars": 45,
                "readme": "# Customer Segmentation Dataset\n\nThis dataset contains anonymized customer transaction data for segmentation analysis.\n\n## Features\n- Customer demographics\n- Purchase history\n- Behavioral metrics\n- Segmentation labels",
                "policies": [
                    {
                        "type": "data-privacy",
                        "description": "GDPR compliant anonymization",
                    },
                    {
                        "type": "usage-rights",
                        "description": "Academic and commercial use allowed",
                    },
                ],
                "connections": [
                    {"type": "rest-api", "description": "RESTful data access"},
                    {"type": "sql", "description": "Direct SQL query access"},
                ],
            },
            {
                "owner": "alice_chen",
                "type": "user",
                "name": "ML Model Performance Benchmarks",
                "slug": "ml-benchmarks",
                "description": "Standardized benchmarks for machine learning model evaluation",
                "visibility": "public",
                "version": "1.3.0",
                "stars": 82,
            },
            # Bob Smith - Machine Learning
            {
                "owner": "bob_smith",
                "type": "user",
                "name": "Image Classification Dataset",
                "slug": "image-classification-v2",
                "description": "Large-scale labeled image dataset for computer vision tasks",
                "visibility": "public",
                "version": "2.0.0",
                "stars": 156,
                "readme": "# Image Classification Dataset v2\n\n50,000 high-resolution images across 100 categories.",
            },
            {
                "owner": "bob_smith",
                "type": "user",
                "name": "Feature Engineering Tools",
                "slug": "feature-engineering",
                "description": "Automated feature engineering pipeline and tools",
                "visibility": "internal",
                "version": "0.8.0",
                "stars": 23,
            },
            # Carol Rodriguez - Bioinformatics
            {
                "owner": "carol_rodriguez",
                "type": "user",
                "name": "Genomic Variant Database",
                "slug": "genomic-variants",
                "description": "Curated database of genomic variants and annotations",
                "visibility": "private",
                "version": "3.2.1",
                "stars": 67,
                "policies": [
                    {
                        "type": "ethical-review",
                        "description": "IRB approved research use only",
                    },
                    {
                        "type": "data-sharing",
                        "description": "Restricted to authorized researchers",
                    },
                ],
            },
            # David Kim - Research
            {
                "owner": "david_kim",
                "type": "user",
                "name": "Academic Citation Network",
                "slug": "citation-network",
                "description": "Comprehensive academic paper citation and collaboration network",
                "visibility": "public",
                "version": "1.0.0",
                "stars": 91,
            },
            {
                "owner": "david_kim",
                "type": "user",
                "name": "Research Collaboration Tools",
                "slug": "collab-tools",
                "description": "Tools for facilitating academic research collaboration",
                "visibility": "public",
                "version": "0.5.0",
                "stars": 34,
            },
            # Emma Jones - Climate
            {
                "owner": "emma_jones",
                "type": "user",
                "name": "Climate Model Outputs",
                "slug": "climate-models-2024",
                "description": "High-resolution climate model projections for 2024-2050",
                "visibility": "public",
                "version": "1.1.0",
                "stars": 128,
                "readme": "# Climate Model Outputs 2024\n\nRegional climate projections with 1km resolution.\n\n## Variables\n- Temperature\n- Precipitation\n- Wind patterns\n- Extreme weather events",
            },
            # Frank Taylor - Finance
            {
                "owner": "frank_taylor",
                "type": "user",
                "name": "Market Risk Analytics",
                "slug": "market-risk",
                "description": "Financial market risk assessment tools and historical data",
                "visibility": "private",
                "version": "2.3.0",
                "stars": 15,
            },
            {
                "owner": "frank_taylor",
                "type": "user",
                "name": "Trading Strategy Backtests",
                "slug": "trading-backtests",
                "description": "Historical backtesting results for quantitative trading strategies",
                "visibility": "internal",
                "version": "1.8.0",
                "stars": 29,
            },
            # Grace Wang - NLP
            {
                "owner": "grace_wang",
                "type": "user",
                "name": "Multilingual Text Corpus",
                "slug": "multilingual-corpus",
                "description": "Large-scale multilingual text dataset for NLP research",
                "visibility": "public",
                "version": "4.0.0",
                "stars": 203,
            },
            # Henry Brown - Physics
            {
                "owner": "henry_brown",
                "type": "user",
                "name": "Quantum Simulation Data",
                "slug": "quantum-simulations",
                "description": "Results from quantum many-body system simulations",
                "visibility": "public",
                "version": "1.2.0",
                "stars": 76,
            },
            # Additional user datasites
            {
                "owner": "iris_zhang",
                "type": "user",
                "name": "Medical Imaging Archive",
                "slug": "medical-imaging",
                "description": "Anonymized medical imaging dataset for AI research",
                "visibility": "private",
                "version": "1.5.0",
                "stars": 89,
            },
            {
                "owner": "jack_wilson",
                "type": "user",
                "name": "Robotics Sensor Data",
                "slug": "robotics-sensors",
                "description": "Multi-modal sensor data from robotic systems",
                "visibility": "public",
                "version": "2.2.0",
                "stars": 54,
            },
            {
                "owner": "kate_miller",
                "type": "user",
                "name": "E-commerce Analytics",
                "slug": "ecommerce-analytics",
                "description": "Customer journey and conversion funnel analytics",
                "visibility": "internal",
                "version": "1.4.0",
                "stars": 37,
            },
            {
                "owner": "leo_garcia",
                "type": "user",
                "name": "Social Media Sentiment",
                "slug": "social-sentiment",
                "description": "Real-time social media sentiment analysis dataset",
                "visibility": "public",
                "version": "3.1.0",
                "stars": 112,
            },
            {
                "owner": "maya_patel",
                "type": "user",
                "name": "Autonomous Vehicle Logs",
                "slug": "av-logs",
                "description": "Self-driving car sensor logs and decision data",
                "visibility": "private",
                "version": "1.0.0",
                "stars": 98,
            },
            {
                "owner": "noah_lee",
                "type": "user",
                "name": "Energy Grid Analytics",
                "slug": "energy-grid",
                "description": "Smart grid performance and optimization data",
                "visibility": "public",
                "version": "2.0.0",
                "stars": 65,
            },
            {
                "owner": "olivia_davis",
                "type": "user",
                "name": "Cybersecurity Threat Intel",
                "slug": "threat-intelligence",
                "description": "Anonymized cybersecurity threat patterns and indicators",
                "visibility": "internal",
                "version": "1.7.0",
                "stars": 143,
            },
        ]

        # Organization-owned datasites
        org_datasets = [
            # Tech Innovation Lab
            {
                "owner": "tech-innovation-lab",
                "type": "organization",
                "created_by": "alice_chen",
                "name": "Innovation Metrics Dashboard",
                "slug": "innovation-metrics",
                "description": "Key performance indicators for technology innovation tracking",
                "visibility": "internal",
                "version": "1.0.0",
                "stars": 28,
            },
            {
                "owner": "tech-innovation-lab",
                "type": "organization",
                "created_by": "grace_wang",
                "name": "Patent Analysis Dataset",
                "slug": "patent-analysis",
                "description": "Technology patent landscape analysis and trends",
                "visibility": "public",
                "version": "2.1.0",
                "stars": 71,
                "readme": "# Patent Analysis Dataset\n\nComprehensive analysis of technology patents from 2020-2024.\n\n## Coverage\n- AI/ML patents\n- Biotechnology\n- Clean energy\n- Quantum computing",
            },
            # BioDataCorp
            {
                "owner": "biodatacorp",
                "type": "organization",
                "created_by": "carol_rodriguez",
                "name": "Protein Structure Database",
                "slug": "protein-structures",
                "description": "Comprehensive protein structure and function database",
                "visibility": "public",
                "version": "5.2.0",
                "stars": 234,
                "policies": [
                    {
                        "type": "open-access",
                        "description": "Freely available for research",
                    },
                    {
                        "type": "attribution",
                        "description": "Citation required for publications",
                    },
                ],
            },
            {
                "owner": "biodatacorp",
                "type": "organization",
                "created_by": "iris_zhang",
                "name": "Clinical Trial Analytics",
                "slug": "clinical-trials",
                "description": "Aggregated clinical trial outcomes and analysis",
                "visibility": "private",
                "version": "1.3.0",
                "stars": 45,
            },
            # Climate Analytics
            {
                "owner": "climate-analytics",
                "type": "organization",
                "created_by": "emma_jones",
                "name": "Global Temperature Archive",
                "slug": "global-temperature",
                "description": "Historical and real-time global temperature measurements",
                "visibility": "public",
                "version": "3.0.0",
                "stars": 187,
            },
            {
                "owner": "climate-analytics",
                "type": "organization",
                "created_by": "noah_lee",
                "name": "Carbon Footprint Calculator",
                "slug": "carbon-calculator",
                "description": "Industry-specific carbon footprint calculation tools",
                "visibility": "public",
                "version": "1.6.0",
                "stars": 92,
            },
            # FinTech Data Solutions
            {
                "owner": "fintech-data",
                "type": "organization",
                "created_by": "frank_taylor",
                "name": "Market Volatility Models",
                "slug": "volatility-models",
                "description": "Advanced volatility modeling and prediction frameworks",
                "visibility": "private",
                "version": "2.4.0",
                "stars": 38,
            },
            {
                "owner": "fintech-data",
                "type": "organization",
                "created_by": "kate_miller",
                "name": "Fraud Detection Patterns",
                "slug": "fraud-patterns",
                "description": "Machine learning models for financial fraud detection",
                "visibility": "internal",
                "version": "1.9.0",
                "stars": 67,
            },
            # AI Research Collective
            {
                "owner": "ai-research-collective",
                "type": "organization",
                "created_by": "grace_wang",
                "name": "Foundation Model Benchmarks",
                "slug": "foundation-benchmarks",
                "description": "Standardized benchmarks for large foundation models",
                "visibility": "public",
                "version": "1.0.0",
                "stars": 312,
                "readme": "# Foundation Model Benchmarks\n\nComprehensive evaluation suite for large language and vision models.\n\n## Test Categories\n- Language understanding\n- Code generation\n- Mathematical reasoning\n- Vision-language tasks",
            },
            {
                "owner": "ai-research-collective",
                "type": "organization",
                "created_by": "jack_wilson",
                "name": "Robotics AI Datasets",
                "slug": "robotics-ai",
                "description": "Curated datasets for robotics AI research",
                "visibility": "public",
                "version": "2.3.0",
                "stars": 156,
            },
            # Healthcare Intelligence
            {
                "owner": "healthcare-intel",
                "type": "organization",
                "created_by": "iris_zhang",
                "name": "Population Health Insights",
                "slug": "population-health",
                "description": "Population-level health trends and predictive analytics",
                "visibility": "internal",
                "version": "1.8.0",
                "stars": 89,
            },
            # Automotive Data Labs
            {
                "owner": "automotive-data-labs",
                "type": "organization",
                "created_by": "maya_patel",
                "name": "Vehicle Performance Metrics",
                "slug": "vehicle-performance",
                "description": "Connected vehicle performance and efficiency data",
                "visibility": "private",
                "version": "1.2.0",
                "stars": 43,
            },
            {
                "owner": "automotive-data-labs",
                "type": "organization",
                "created_by": "olivia_davis",
                "name": "Traffic Safety Analytics",
                "slug": "traffic-safety",
                "description": "Road safety analysis and accident prevention insights",
                "visibility": "public",
                "version": "2.0.0",
                "stars": 78,
            },
            # Open Science Foundation
            {
                "owner": "open-science-foundation",
                "type": "organization",
                "created_by": "david_kim",
                "name": "Open Research Repository",
                "slug": "open-research",
                "description": "Centralized repository for open science research data",
                "visibility": "public",
                "version": "4.1.0",
                "stars": 289,
                "readme": "# Open Research Repository\n\nPromoting open science through freely accessible research data.\n\n## Mission\nDemocratize access to scientific knowledge and accelerate research collaboration.",
                "policies": [
                    {
                        "type": "open-access",
                        "description": "CC0 - Public domain dedication",
                    },
                    {
                        "type": "quality-review",
                        "description": "Peer-reviewed data submissions",
                    },
                ],
            },
        ]

        # Create user datasites
        for dataset in user_datasets:
            await self._create_datasite(client, dataset)

        # Create organization datasites
        for dataset in org_datasets:
            await self._create_datasite(client, dataset)

        print(f"✅ Created {len(user_datasets) + len(org_datasets)} datasites")

    async def _create_datasite(self, client: httpx.AsyncClient, config: dict) -> None:
        """Create a single datasite."""
        try:
            if config["type"] == "user":
                # User-owned datasite
                owner = config["owner"]
                headers = {"Authorization": f"Bearer {self.auth_tokens[owner]}"}
                url = f"{self.api_url}/datasites/"

            else:
                # Organization-owned datasite
                creator = config["created_by"]
                headers = {"Authorization": f"Bearer {self.auth_tokens[creator]}"}
                url = f"{self.api_url}/datasites/"

                # Add organization_id to the payload
                org_slug = config["owner"]
                org_id = self.organizations[org_slug]["id"]
                config["organization_id"] = org_id

            # Prepare datasite payload
            datasite_data = {
                "name": config["name"],
                "slug": config["slug"],
                "description": config["description"],
                "visibility": config["visibility"],
                "version": config["version"],
                "readme": config.get("readme", ""),
                "policies": config.get("policies", []),
                "connect": config.get("connections", []),
            }

            # Add organization_id if present
            if "organization_id" in config:
                datasite_data["organization_id"] = config["organization_id"]

            response = await client.post(url, json=datasite_data, headers=headers)
            response.raise_for_status()

            datasite = response.json()

            # Simulate stars by updating the count
            if "stars" in config and config["stars"] > 0:
                await self._update_stars(
                    client, datasite["id"], config["stars"], headers
                )

            owner_display = (
                config["owner"]
                if config["type"] == "user"
                else f"{config['owner']} (org)"
            )
            print(f"  ✅ Created datasite: {config['name']} ({owner_display})")

        except httpx.HTTPStatusError as e:
            print(f"  ❌ Failed to create {config['name']}: {e.response.text}")
            # Don't raise to continue with other datasites

    async def _update_stars(
        self,
        client: httpx.AsyncClient,
        datasite_id: int,
        star_count: int,
        headers: dict,
    ) -> None:
        """Simulate star count by updating datasite manually."""
        # Note: This is a simulation since the actual starring endpoint
        # would require individual user actions
        try:
            update_data = {"stars_count": star_count}
            await client.patch(
                f"{self.api_url}/datasites/{datasite_id}",
                json=update_data,
                headers=headers,
            )
            # Don't raise on failure - stars are not critical
        except Exception:
            pass  # Ignore star update failures


async def main():
    """Main entry point for the seeding script."""
    seeder = SyfthubSeeder()
    await seeder.seed_all()


if __name__ == "__main__":
    asyncio.run(main())
