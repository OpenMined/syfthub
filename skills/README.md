# SyftHub Skills

This directory contains Claude Code skills for working with SyftHub.

## Available Skills

| Skill | Description |
|-------|-------------|
| [syfthub-cli](./syfthub-cli/) | CLI commands for authentication, endpoint discovery, RAG queries, and configuration |

## Installation

### Option 1: Copy to Claude Code skills directory

```bash
# Clone or navigate to the syfthub repo
cp -r skills/syfthub-cli ~/.claude/skills/
```

### Option 2: Symlink (for development)

```bash
ln -s "$(pwd)/skills/syfthub-cli" ~/.claude/skills/syfthub-cli
```

### Option 3: One-liner install

```bash
curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/skills/syfthub-cli/SKILL.md -o ~/.claude/skills/syfthub-cli/SKILL.md --create-dirs
```

## Verify Installation

After installation, the skill will automatically trigger when you ask Claude Code about:
- SyftHub CLI commands (`syft login`, `syft ls`, `syft query`, etc.)
- Browsing or listing AI endpoints
- RAG queries with SyftHub
- Managing aggregator configurations
