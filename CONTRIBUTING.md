# Contributing to Pydantic Documentation MCP Server

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Code of Conduct

Be respectful, professional, and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.12+
- uv package manager
- Git

### Development Setup

1. **Fork and clone the repository:**
```bash
git clone https://github.com/yourusername/mcp_pydantic_docs.git
cd mcp_pydantic_docs
```

2. **Create a virtual environment and install dependencies:**
```bash
uv sync
```

3. **Build search indices:**
```bash
uv run python -m mcp_pydantic_docs.indexer
```

4. **Verify installation:**
```bash
uv run mcp-pydantic-docs
```

## Development Workflow

### Branch Strategy

- `main` - Stable release branch
- `develop` - Development branch (if used)
- Feature branches: `feature/description`
- Bug fix branches: `fix/description`

### Making Changes

1. **Create a feature branch:**
```bash
git checkout -b feature/your-feature-name
```

2. **Make your changes:**
- Write clean, documented code
- Follow existing code style
- Add tests for new functionality
- Update documentation as needed

3. **Test your changes:**
```bash
# Run tests (if available)
uv run pytest

# Check code quality
uv run black mcp_pydantic_docs/
uv run ruff check mcp_pydantic_docs/
uv run mypy mcp_pydantic_docs/

# Test the server
uv run mcp-pydantic-docs
```

4. **Commit your changes:**
```bash
git add .
git commit -m "feat: add new feature description"
```

Use conventional commit messages:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

5. **Push to your fork:**
```bash
git push origin feature/your-feature-name
```

6. **Create a Pull Request:**
- Go to the original repository on GitHub
- Click "New Pull Request"
- Select your fork and branch
- Fill in the PR template with:
  - Description of changes
  - Related issues (if any)
  - Testing performed
  - Screenshots (if applicable)

## Pull Request Guidelines

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests pass locally
- [ ] Documentation updated (if applicable)
- [ ] Commit messages follow conventional commits
- [ ] No merge conflicts with main branch
- [ ] PR description clearly explains the changes

### Code Style

- Use Black for code formatting (line length: 88)
- Follow PEP 8 guidelines
- Use type hints for function signatures
- Document complex logic with comments
- Keep functions focused and modular

### Testing

- Add tests for new features
- Ensure existing tests pass
- Test edge cases
- Verify search functionality works correctly

## Project Structure

```
mcp_pydantic_docs/
├── mcp_pydantic_docs/
│   ├── mcp.py          # MCP server implementation
│   ├── indexer.py      # Search index builder
│   ├── normalize.py    # HTML to JSONL converter
│   └── setup.py        # Setup utilities
├── data/               # Search data
├── tests/              # Test files (if present)
├── pyproject.toml      # Package configuration
└── README.md           # Documentation
```

## Types of Contributions

### Bug Reports

- Use GitHub Issues
- Include:
  - Clear description of the bug
  - Steps to reproduce
  - Expected vs actual behavior
  - Environment details (OS, Python version, etc.)
  - Error messages or logs

### Feature Requests

- Use GitHub Issues
- Include:
  - Clear description of the feature
  - Use case and motivation
  - Proposed implementation (if applicable)
  - Examples of similar features

### Documentation

- Fix typos or unclear sections
- Add examples
- Improve setup instructions
- Update API documentation

### Code Contributions

- Bug fixes
- New features
- Performance improvements
- Code refactoring
- Test improvements

## Review Process

1. Maintainers will review your PR
2. Address any requested changes
3. Once approved, your PR will be merged
4. Your contribution will be included in the next release

## Additional Notes

### Rebuilding Search Indices

If you modify JSONL data:
```bash
uv run python -m mcp_pydantic_docs.indexer
```

### Updating Documentation Data

To download latest Pydantic docs:
```bash
uv run python -m mcp_pydantic_docs.setup --download --build-index
```

### Running the Server Locally

```bash
uv run mcp-pydantic-docs
```

## Questions?

- Open an issue for questions
- Check existing issues and PRs first
- Be patient and respectful

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
