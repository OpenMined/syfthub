# Syfthub Data Seeding Scripts

This directory contains scripts to populate your Syfthub instance with realistic sample data for testing and development.

## Quick Start

1. **Start your Syfthub server**:
   ```bash
   # Option 1: Using Make
   make run

   # Option 2: Using Docker Compose
   docker-compose up -d

   # Option 3: Direct Python
   python -m syfthub.main
   ```

2. **Run the seeding script**:
   ```bash
   cd scripts/
   ./run_seed.sh
   ```

   Or manually:
   ```bash
   pip install httpx>=0.28.0
   python seed_data.py
   ```

## What Gets Created

### 👥 Users (15 total)
Diverse user profiles across different domains:
- **Tech Professionals**: alice_chen, bob_smith, jack_wilson
- **Researchers**: david_kim, emma_jones, henry_brown
- **Data Scientists**: kate_miller, leo_garcia, frank_taylor
- **Domain Specialists**: carol_rodriguez (bioinformatics), grace_wang (NLP), iris_zhang (healthcare), maya_patel (automotive), noah_lee (energy), olivia_davis (cybersecurity)

### 🏢 Organizations (8 total)
Multi-domain organizations with memberships:
- **Tech Innovation Lab** - Technology R&D
- **BioDataCorp** - Bioinformatics solutions
- **Climate Analytics** - Environmental data
- **FinTech Data Solutions** - Financial technology
- **AI Research Collective** - AI research collaboration
- **Healthcare Intelligence** - Medical data analytics
- **Automotive Data Labs** - Connected vehicle data
- **Open Science Foundation** - Open access research

### 📊 Datasites (35+ total)

#### User-Owned Datasites (18)
- Customer segmentation datasets
- Machine learning benchmarks
- Image classification data
- Genomic variant databases
- Climate model outputs
- Financial risk analytics
- NLP text corpora
- Quantum simulation results
- Medical imaging archives
- Robotics sensor data
- And more...

#### Organization-Owned Datasites (15)
- Innovation metrics dashboards
- Patent analysis datasets
- Protein structure databases
- Global temperature archives
- Market volatility models
- Foundation model benchmarks
- Population health insights
- Vehicle performance metrics
- Open research repositories
- And more...

## Features Demonstrated

### 🔐 Authentication & Authorization
- JWT-based user authentication
- Role-based access control
- Organization membership management

### 🌐 Multi-tenancy
- User-owned datasites
- Organization-owned datasites
- Mixed ownership scenarios

### 🔒 Visibility Controls
- **Public**: Openly accessible datasites
- **Internal**: Authenticated user access only
- **Private**: Owner/member access only

### 📋 Rich Metadata
- Semantic versioning
- README documentation
- Policy configurations
- Connection specifications
- Star ratings simulation

### 🏗️ Realistic Data Structure
- Domain-specific datasets
- Varied complexity levels
- Professional descriptions
- Authentic use cases

## Sample API Endpoints to Test

After seeding, try these endpoints:

```bash
# Get user datasites
curl http://localhost:8000/alice_chen

# Get organization datasites
curl http://localhost:8000/tech-innovation-lab

# View specific datasite
curl http://localhost:8000/alice_chen/customer-segmentation

# API endpoints
curl http://localhost:8000/api/v1/datasites/
curl http://localhost:8000/api/v1/organizations/
curl http://localhost:8000/api/v1/users/

# Trending datasites
curl "http://localhost:8000/api/v1/datasites/trending?min_stars=50"
```

## Authentication for API Testing

The seeding script creates users with predictable credentials for testing:

```python
# Example credentials (username: password)
alice_chen: DataScience123!
bob_smith: MachineLearning456!
carol_rodriguez: Genomics789!
# ... and so on
```

To authenticate and access protected endpoints:
```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice_chen", "password": "DataScience123!"}'

# Use the returned access_token in subsequent requests
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/v1/datasites/me
```

## Script Components

- **`seed_data.py`** - Main seeding script with comprehensive data creation
- **`run_seed.sh`** - Bash wrapper with environment checks
- **`requirements.txt`** - Python dependencies
- **`README.md`** - This documentation

## Customization

You can modify `seed_data.py` to:
- Add more users/organizations
- Create different datasite types
- Adjust visibility distributions
- Modify star count simulations
- Add custom policies/connections

## Troubleshooting

### Server Connection Issues
```bash
# Check if server is running
curl http://localhost:8000/health

# Start server if needed
make run
# or
docker-compose up -d
```

### Permission Issues
```bash
# Make script executable
chmod +x run_seed.sh

# Install dependencies manually
pip install httpx>=0.28.0
```

### Data Already Exists
If you've already run the script, you may get conflicts. Either:
1. Reset your database
2. Modify usernames/slugs in the script
3. Clear existing data via API

## Production Considerations

⚠️ **This script is for development/testing only!**

For production:
- Use secure password policies
- Implement proper data governance
- Set up monitoring and logging
- Use environment-based configuration
- Implement proper backup strategies

---

**Happy testing!** 🚀
