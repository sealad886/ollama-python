# Ollama Python Library

The Ollama Python library provides the easiest way to integrate Python 3.8+ projects with [Ollama](https://github.com/ollama/ollama). This is a client library for interfacing with the Ollama REST API, featuring sync/async clients, streaming responses, tool calling, and multimodal capabilities.

**ALWAYS reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Known Issues to Address First

⚠️ **CRITICAL**: The current codebase has **indentation syntax errors** in `ollama/_client.py` at line 154+ that prevent basic import. This is due to inconsistent indentation (mixing 2-space and 4-space) introduced during signing functionality integration.

**Before making any changes, fix the indentation issues:**
```bash
# Download working version from main ollama repo
curl -s https://raw.githubusercontent.com/ollama/ollama-python/main/ollama/_client.py > ollama/_client_working.py
# Replace the broken file temporarily
cp ollama/_client_working.py ollama/_client.py
# Test import works
python -c "import ollama; print('Success')"
```

## Working Effectively

### Bootstrap and Install Dependencies
```bash
# Install uv package manager (if not available)
pip install uv

# Sync dependencies and create virtual environment
uv sync
```

### Build and Test (NEVER CANCEL - All commands complete quickly)
```bash
# Run all tests - takes ~6 seconds. NEVER CANCEL: Set timeout to 30+ seconds
uvx hatch test -acp

# Check code formatting - takes <1 second. NEVER CANCEL: Set timeout to 15+ seconds  
uvx hatch fmt --check -f

# Check linting - takes <1 second. NEVER CANCEL: Set timeout to 15+ seconds
uvx hatch fmt --check -l

# Build package - takes <1 second. NEVER CANCEL: Set timeout to 15+ seconds
uv build

# Verify lock file consistency - takes <1 second
uv lock --check

# Verify requirements.txt is current - takes <1 second
uv export >requirements.txt.new && diff requirements.txt requirements.txt.new
```

### Run the Library and Examples
```bash
# ALWAYS fix syntax issues first before attempting to run anything

# Basic import test (requires fixed _client.py)
python -c "import ollama; print('ollama imported successfully')"

# Run examples (they will show connection errors without Ollama server, which is expected)
python examples/list.py
python examples/generate.py
python examples/chat.py

# Install and run Ollama server locally for full testing (optional)
# Note: Examples fail with ConnectionError if Ollama server is not running - this is normal
```

## Validation Steps

### Code Quality Validation
**ALWAYS run these before committing changes:**
```bash
# Format code automatically
uvx hatch fmt

# Run linting
uvx hatch fmt --check -l --output-format=github

# Run full test suite
uvx hatch test -acp
```

### Manual Testing Scenarios  
**After making changes, manually validate with these scenarios:**

1. **Basic Import Test**: `python -c "import ollama; print('Success')"`
2. **Example Execution**: Run 2-3 examples from `examples/` directory and verify they show expected ConnectionError (not import errors)
3. **Type Checking**: Verify `from ollama import ChatResponse, Client, AsyncClient` works
4. **Build Test**: Run `uv build` and verify wheel creation succeeds

## Project Structure

### Repository Layout
```
├── ollama/              # Main library code
│   ├── __init__.py      # Public API exports  
│   ├── _client.py       # Sync/async HTTP clients (⚠️ BROKEN INDENTATION)
│   ├── _types.py        # Pydantic models and type definitions
│   ├── _utils.py        # Utility functions (function-to-tool conversion)
│   ├── _auth.py         # Ed25519 signing for authentication
│   └── _signing.py      # Request signing logic integration
├── examples/            # Usage examples for all API features
├── tests/               # Test suite (pytest-based, ~81 tests)
├── pyproject.toml       # Project config, dependencies, build system
├── uv.lock             # Dependency lock file
├── requirements.txt     # Generated from uv.lock for compatibility
└── .github/workflows/   # CI/CD automation
```

### Key Dependencies
- **httpx** (>=0.27): HTTP client for sync/async requests
- **pydantic** (>=2.9): Data validation and type safety
- **cryptography**: Ed25519 signing (optional, for authentication)

### Development Workflow Tools
- **uv**: Fast Python package manager and dependency resolver
- **hatch**: Build system, test runner, and formatter orchestration  
- **ruff**: Fast Python linter and formatter (configured for 2-space indentation)
- **pytest**: Test framework with anyio, httpserver, and mock plugins

## Common Tasks

### Making Code Changes
1. **ALWAYS** fix the indentation issue in `_client.py` first
2. Make your changes using minimal modifications
3. Run `uvx hatch fmt` to auto-format code (uses 2-space indentation)
4. Run `uvx hatch test` to verify tests pass  
5. Manually test with import and example execution

### Adding New Features
1. Update type definitions in `_types.py` if needed
2. Implement client methods in `_client.py` (both sync and async versions)
3. Add comprehensive tests in `tests/`
4. Create usage examples in `examples/`
5. Update README.md documentation

### Working with Examples
- All examples in `examples/` directory demonstrate different API features
- Examples expect Ollama server running on `localhost:11434` by default
- **Expected behavior without server**: `ConnectionError: Failed to connect to Ollama...`
- **Test examples by**: `python examples/<name>.py`

### Testing Strategy
- **Unit tests**: Mock HTTP responses using `pytest-httpserver`
- **No external dependencies**: Tests don't require Ollama server
- **Fast execution**: Full test suite runs in ~6 seconds
- **Coverage areas**: Client methods, type serialization, utility functions

## Build and CI Information

### GitHub Actions Workflow
The CI pipeline (`.github/workflows/test.yaml`) runs:
1. Tests across Python 3.8-3.13: `uvx hatch test -acp`
2. Format checking: `uvx hatch fmt --check -f`  
3. Lint checking: `uvx hatch fmt --check -l --output-format=github`
4. Lock file validation: `uv lock --check`
5. Requirements sync check: `uv export >requirements.txt && git diff --exit-code requirements.txt`

### Expected Timing (NEVER CANCEL)
- **Dependency sync**: ~2-3 seconds
- **Test execution**: ~6 seconds total (NEVER CANCEL: Set timeout to 30+ seconds)
- **Formatting/linting**: <1 second each (NEVER CANCEL: Set timeout to 15+ seconds)
- **Build**: <1 second (NEVER CANCEL: Set timeout to 15+ seconds)
- **Lock file check**: <1 second

### Error Patterns to Expect
- **IndentationError in _client.py**: Known issue, fix with working version from main repo
- **ConnectionError in examples**: Normal when Ollama server not running
- **Formatting differences**: Code uses 2-space indentation per ruff config

## Quick Reference Commands
```bash
# Setup environment
uv sync

# Fix syntax issue first
curl -s https://raw.githubusercontent.com/ollama/ollama-python/main/ollama/_client.py > ollama/_client.py

# Development workflow
uvx hatch fmt                    # Auto-format code
uvx hatch test                   # Run tests (6 seconds)
uv build                         # Build package (1 second)
python examples/list.py          # Test basic functionality

# Validation before commit
uvx hatch fmt --check -f         # Check formatting
uvx hatch fmt --check -l         # Check linting  
uvx hatch test -acp              # Full test with coverage
uv lock --check                  # Verify dependencies
```