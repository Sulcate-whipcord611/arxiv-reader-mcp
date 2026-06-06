Contributions are welcome. Open an issue or pull request on GitHub.

## Development Setup

```bash
git clone <repo-url>
cd arxiv-mcp-server
uv sync
```

## Running Tests

```bash
uv run pytest
```

To run a specific test file:

```bash
uv run pytest tests/test_parser.py
```

## Code Style

Keep functions focused and avoid unnecessary comments. Use type hints for all public functions.

## Pull Request Process

1. Open an issue describing the change before working on it.
2. Fork the repo and create a branch from `main`.
3. Write tests for any new functionality.
4. Ensure all tests pass before submitting.
5. Keep PRs focused on a single concern.
6. Update the README if adding new tools or changing behavior.
