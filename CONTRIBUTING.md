# Contributing to Syfthub

Thank you for your interest in contributing to Syfthub! This document provides guidelines and instructions for contributing.

## Development Setup

1. Fork the repository and clone your fork:
```bash
git clone https://github.com/YOUR_USERNAME/syfthub.git
cd syfthub
```

2. Install uv if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Install the development dependencies:
```bash
uv sync --dev
```

4. Install pre-commit hooks:
```bash
uv run pre-commit install
```

## Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for both linting and formatting. The configuration is in `pyproject.toml`.

Before committing:
- Format your code: `uv run ruff format src/ tests/`
- Check linting: `uv run ruff check src/ tests/`
- Run type checking: `uv run mypy src/`

## Testing

All code changes should include tests. We use pytest for testing.

- Run all tests: `uv run pytest`
- Run with coverage: `uv run pytest --cov`
- Run specific test file: `uv run pytest tests/test_main.py`

## Commit Messages

Please use clear and descriptive commit messages:
- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and pull requests when relevant

## Pull Request Process

1. Create a new branch for your feature or bugfix:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and ensure all tests pass

3. Run the full test suite:
```bash
uv run pre-commit run --all-files
uv run pytest
uv run mypy src/
```

4. Commit your changes with a descriptive message

5. Push to your fork and create a pull request

6. Ensure all CI checks pass

7. Request review from maintainers

## Code Review

All submissions require review. We use GitHub pull requests for this purpose.

## Issues

Feel free to submit issues and enhancement requests.

## Questions?

Feel free to open an issue with your question or reach out to the maintainers.

Thank you for contributing!
