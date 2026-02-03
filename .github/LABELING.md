# Issue Labeling System

This document describes the automated issue labeling system for SyftHub.

## Overview

SyftHub uses an automated GitHub Actions workflow to label issues based on their content. This helps maintainers and contributors quickly understand and prioritize issues.

## Label Categories

### Area Labels (Blue - `#0075ca`)

These labels identify which component or area of the project an issue relates to:

- `area: backend` - Backend/API related issues (FastAPI, Python)
- `area: frontend` - Frontend related issues (React, TypeScript)
- `area: sdk` - SDK related issues (Python/TypeScript SDKs)
- `area: devops` - DevOps, CI/CD, Docker, deployment issues
- `area: database` - Database related issues (PostgreSQL, migrations)
- `area: auth` - Authentication and authorization issues
- `area: organizations` - Organization management features
- `area: endpoints` - Endpoint management features
- `area: documentation` - Documentation improvements

### Type Labels

These labels identify the type of issue:

- `type: bug` (Red - `#d73a4a`) - Something isn't working
- `type: enhancement` (Cyan - `#a2eeef`) - New feature or request
- `type: refactor` (Yellow - `#fbca04`) - Code refactoring or cleanup
- `type: performance` (Pink - `#f9d0c4`) - Performance improvements
- `type: testing` (Blue - `#c5def5`) - Testing related changes
- `type: question` (Purple - `#d876e3`) - Further information is requested

### Priority Labels

These labels indicate the urgency of an issue:

- `priority: high` (Dark Red - `#b60205`) - High priority issue
- `priority: medium` (Yellow - `#fbca04`) - Medium priority issue
- `priority: low` (Light Blue - `#c5def5`) - Low priority issue

### Status Labels

These labels track the current state of an issue:

- `status: needs-triage` (Gray - `#ededed`) - Needs to be triaged by maintainers
- `status: in-progress` (Light Yellow - `#fef2c0`) - Currently being worked on
- `status: blocked` (Orange - `#d93f0b`) - Blocked by another issue or external dependency
- `status: needs-info` (Gray - `#ededed`) - More information needed from reporter

### Community Labels

These labels help community members find issues to contribute to:

- `good first issue` (Purple - `#7057ff`) - Good for newcomers
- `help wanted` (Green - `#008672`) - Extra attention is needed

### Special Labels

- `security` (Dark Red - `#b60205`) - Security vulnerability or concern
- `breaking change` (Red - `#d73a4a`) - Changes that break backwards compatibility
- `duplicate` (Gray - `#cfd3d7`) - This issue or pull request already exists
- `wontfix` (White - `#ffffff`) - This will not be worked on
- `invalid` (Light Yellow - `#e4e669`) - This doesn't seem right

## How Automatic Labeling Works

The automated labeling workflow (`.github/workflows/label-issues.yml`) runs when:
- A new issue is opened
- An existing issue is edited

The workflow analyzes the issue title and body for keywords and automatically applies relevant labels:

### Area Detection

Issues are labeled based on component mentions:
- Backend keywords: "backend", "api", "fastapi"
- Frontend keywords: "frontend", "react", "ui", "typescript"
- SDK keywords: "sdk", "python sdk", "typescript sdk"
- DevOps keywords: "docker", "deployment", "ci/cd", "github actions"
- Database keywords: "database", "postgres", "sql", "migration"
- Auth keywords: "auth", "authentication", "login", "token", "jwt"

### Type Detection

Issue types are identified by:
- **Bugs**: "bug", "error", "fix", "broken", "exception", "stack trace"
- **Features**: "feature", "enhancement", "add", "support for"
- **Refactors**: "refactor", "clean up", "technical debt"
- **Performance**: "performance", "slow", "optimization"
- **Questions**: "how to", "question", "?"

### Priority Detection

High priority is automatically assigned for:
- **Security issues**: "security", "vulnerability", "CVE"
- **Critical bugs**: "critical", "urgent", "production down"

### Welcome Messages

First-time contributors receive an automated welcome message when they open their first issue, with links to:
- Contributing guidelines
- Project documentation
- Community resources

## Setting Up Labels

To create or update all labels in the repository, manually trigger the "Setup Repository Labels" workflow:

1. Go to Actions → Setup Repository Labels
2. Click "Run workflow"
3. Wait for completion

This workflow is idempotent and will create missing labels or update existing ones to match the configuration.

## Issue Templates

SyftHub provides structured issue templates to help users provide all necessary information:

- **Bug Report** (`bug_report.yml`) - For reporting bugs and errors
- **Feature Request** (`feature_request.yml`) - For suggesting new features
- **Question** (`question.yml`) - For asking questions or seeking help

These templates automatically apply initial labels and guide users to provide relevant information.

## Manual Labeling

Maintainers can also manually add, remove, or change labels as needed. The automated system is a starting point, not a replacement for human judgment.

### Best Practices for Manual Labeling

1. **Review automated labels** - Check that automatically applied labels are correct
2. **Add priority labels** - If the automation didn't add a priority, consider adding one
3. **Update status labels** - Move issues through the workflow with status labels
4. **Use community labels** - Mark appropriate issues as "good first issue" or "help wanted"
5. **Security triage** - Immediately triage any security-labeled issues

## Contributing to the Labeling System

To improve the automated labeling system:

1. Edit `.github/workflows/label-issues.yml` to add new keywords or logic
2. Edit `.github/workflows/setup-labels.yml` to add new label definitions
3. Test your changes in a fork before submitting a PR
4. Update this documentation to reflect any changes

## Example Label Combinations

Here are some common label combinations:

- `type: bug` + `area: backend` + `priority: high` - Critical backend bug
- `type: enhancement` + `area: frontend` + `good first issue` - UI feature good for newcomers
- `type: question` + `area: sdk` - SDK usage question
- `type: bug` + `security` + `priority: high` - Security vulnerability
- `type: refactor` + `area: database` + `status: in-progress` - Database refactoring in progress

## Monitoring and Maintenance

Maintainers should regularly:

1. Review issues labeled `status: needs-triage`
2. Check that automated labels are accurate
3. Update issue templates and labeling logic based on feedback
4. Close duplicate or invalid issues
5. Respond to security-labeled issues immediately

## Questions?

If you have questions about the labeling system, please:
- Open an issue with the `type: question` label
- Check the [Contributing Guide](../CONTRIBUTING.md)
- Ask in [GitHub Discussions](https://github.com/OpenMined/syfthub/discussions)
