# Installation & Setup

## Requirements

- **Python** >= 3.11
- **pip** (latest recommended)
- **Rust** >= 1.75 (optional, for building the native engine from source)
- **VS Build Tools 2022** (Windows only, for Rust compilation)

## Install from PyPI

```bash
pip install vorte
```

This installs the core framework with all Python dependencies. The Rust engine wheel is included for major platforms (Windows, macOS, Linux).

## Optional Dependencies

### AI Providers

```bash
pip install vorte[ai]
```

Includes: `openai>=1.60.0`, `anthropic>=0.40.0`, `google-generativeai>=0.8.0`

### Payments (Stripe)

```bash
pip install vorte[payments]
```

### Search (MeiliSearch)

```bash
pip install vorte[search]
```

### Cloud Storage (S3)

```bash
pip install vorte[storage]
```

### WASM Sandbox

```bash
pip install vorte[sandbox]
```

### Everything

```bash
pip install vorte[full]
```

### Development Tools

```bash
pip install vorte[dev]
```

Includes: `pytest>=8.0.0`, `pytest-asyncio>=0.24.0`, `httpx>=0.28.0`, `ruff>=0.8.0`, `mypy>=1.13.0`

## Verify Installation

```bash
vorte --help
```

```python
python -c "from vorte import Vorte; print(Vorte.__module__)"
```

## Building the Rust Engine from Source

If a pre-built wheel is not available for your platform:

```bash
# Install build dependencies
pip install maturin

# Clone the repository
git clone https://github.com/Lijohtech-Developers/vorte-framework.git
cd vorte-framework

# Build and install
maturin develop --release
```

### Environment Setup

Create a `.env` file in your project root:

```env
VORTE_APP_NAME=My App
VORTE_APP_ENV=development
VORTE_APP_DEBUG=true
VORTE_APP_URL=http://localhost:8000
VORTE_APP_KEY=your-secret-key

VORTE_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb
VORTE_REDIS_URL=redis://localhost:6379/0

VORTE_AUTH_SECRET_KEY=your-jwt-secret
VORTE_AUTH_STRATEGY=jwt
```

All environment variables are prefixed with `VORTE_`. See [Configuration](configuration.md) for the complete list.
