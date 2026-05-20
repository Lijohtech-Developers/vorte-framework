# Contributing to Vorte Framework

Thank you for your interest in contributing to the Vorte Framework! This guide will help you get started.

## Code of Conduct

Be respectful, constructive, and inclusive. We are all here to build something great together.

## Getting Started

### Prerequisites

- **Python** >= 3.11
- **Rust** >= 1.75 (for native engine development)
- **Git**
- **VS Build Tools 2022** (Windows only, for Rust compilation)

### Setup

1. **Fork the repository** on GitHub

2. **Clone your fork**:
```bash
git clone https://github.com/YOUR_USERNAME/vorte-framework.git
cd vorte-framework
```

3. **Create a virtual environment**:
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

4. **Install development dependencies**:
```bash
pip install -e ".[dev]"
```

5. **Build the Rust engine** (optional, for native development):
```bash
pip install maturin
maturin develop --release
```

## Development Workflow

### Create a Branch

```bash
git checkout -b feature/my-new-feature
# or
git checkout -b fix/my-bug-fix
```

### Make Changes

Follow the coding conventions below. Write tests for new features.

### Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_app.py

# Run with verbose output
pytest -v

# Run specific test
pytest tests/test_app.py::test_app_initialization
```

### Run Linting

```bash
# Ruff linter
ruff check .

# Ruff formatter
ruff format .

# Type checking
mypy vorte/
```

### Commit Changes

Use clear, descriptive commit messages following [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(module): add new feature
fix(auth): resolve token expiry issue
docs(readme): update installation guide
test(queue): add backpressure tests
refactor(core): simplify DI container
chore(deps): update dependencies
```

### Push and Create a Pull Request

```bash
git push origin feature/my-new-feature
```

Then create a Pull Request on GitHub.

## Coding Conventions

### Python Style

- **Target**: Python 3.11+
- **Line length**: 100 characters (configured in `pyproject.toml`)
- **Linter**: Ruff
- **Type hints**: Use type hints for all function signatures
- **Async**: Prefer `async/await` for I/O operations

### Code Organization

- **Core**: `vorte/core/` -- Framework internals (app, config, DI, router, etc.)
- **Modules**: `vorte/modules/` -- Feature modules (auth, ai, database, etc.)
- **CLI**: `vorte/cli/` -- Command-line interface
- **Middleware**: `vorte/middleware/` -- HTTP middleware
- **Testing**: `vorte/testing/` -- Test utilities
- **Engine**: `vorte-engine/` -- Rust native engine

### Module Structure

Each module follows this pattern:

```
modules/my_module/
├── __init__.py       # Module class, public exports
├── router.py         # Route definitions (optional)
├── service.py        # Business logic (optional)
├── models.py         # Database models (optional)
├── schemas.py        # Pydantic schemas (optional)
└── events.py         # Event handlers (optional)
```

### Module Guidelines

- Extend the `Module` base class from `vorte.core.module`
- Define `meta` with `ModuleMeta`
- Implement `register(app)` method
- Use `on_startup()` and `on_shutdown()` for lifecycle management
- Implement `health_check()` for monitoring

### Rust Style

- Follow standard Rust conventions (`cargo fmt`, `cargo clippy`)
- Use `#[repr(C)]` for FFI-safe types
- Release the GIL during I/O operations
- Use `Arc<Mutex<>>` sparingly; prefer lock-free patterns

## Adding a New Module

1. Create the module directory in `vorte/modules/`
2. Create `__init__.py` with the module class
3. Define `ModuleMeta` with name, priority, and dependencies
4. Implement the `register(app)` method
5. Add the module to `vorte/__init__.py` exports
6. Add the module to `Vorte._get_builtin_modules()` in `vorte/core/app.py`
7. Write tests in `tests/`
8. Add documentation in `docs/guides/`

## Testing

### Test Structure

```
tests/
├── test_app.py              # Application lifecycle
├── test_module.py           # Module system
├── test_router.py           # Routing and versioning
├── test_response.py         # Response envelope
├── test_di.py               # Dependency injection
├── test_serializer.py       # Serialization
├── test_executor.py         # Executor
├── test_queue.py            # Queue module
└── ...
```

### Writing Tests

- Use `pytest` with `pytest-asyncio`
- `asyncio_mode = "auto"` is configured (no need for `@pytest.mark.asyncio`)
- Use `VorteTestClient` from `vorte.testing` for API tests
- Use `AIMocker` for AI-related tests
- Use `MpesaMocker` for M-Pesa-related tests

### Example Test

```python
import pytest
from vorte import Vorte
from vorte.testing import VorteTestClient

@pytest.fixture
async def client():
    app = Vorte()
    async with VorteTestClient(app) as client:
        yield client

async def test_health_endpoint(client):
    response = await client.get("/health")
    response.assert_success()
```

## Pull Request Guidelines

- **One feature per PR** -- Keep PRs focused
- **Include tests** -- All new features must have tests
- **Update documentation** -- Update relevant docs in `docs/`
- **Pass CI** -- All tests and linting must pass
- **Describe changes** -- Write a clear PR description

## Release Process

1. Update version in `vorte/__init__.py` and `pyproject.toml`
2. Update `CHANGELOG.md` with the new version
3. Commit with message: `bump: release v1.x.x`
4. Tag: `git tag v1.x.x`
5. Push: `git push && git push --tags`
6. Create a GitHub Release with changelog notes
7. CI automatically builds wheels and publishes to PyPI

## Questions?

Open an issue on [GitHub](https://github.com/Lijohtech-Developers/vorte-framework/issues) or start a discussion.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
