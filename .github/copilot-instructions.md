# Ollama Python Library

The Ollama Python library provides the easiest way to integrate Python 3.8+ projects with [Ollama](https://github.com/ollama/ollama). This is a Python SDK for the Ollama API that handles chat, generation, embedding, and model management.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Bootstrap and Development Setup
- Install uv package manager: `pip install uv`
- Set up the development environment: `uv sync` (takes ~2 seconds)
- Verify installation: `uv --version`

### Build and Package
- Build the package: `uv build` (takes ~1 second, NEVER CANCEL)
- Export dependencies: `uv export > requirements.txt` (takes <1 second)
- Check lock file: `uv lock --check` (takes <1 second)

### Code Quality and Linting
- Format code: `uvx hatch fmt` (takes ~1 second, NEVER CANCEL)
- Check formatting: `uvx hatch fmt --check` (takes ~1 second)
- Check linting only: `uvx hatch fmt --check -l` (takes ~1 second)
- **WARNING**: The current codebase has indentation issues in `ollama/_client.py` that prevent tests from running
- **CRITICAL**: Always run `uvx hatch fmt --check -f` before commits or CI will fail

### Testing
- **CURRENT LIMITATION**: Tests cannot run due to syntax errors in codebase
- When syntax issues are fixed, run: `uvx hatch test` (estimated 10-30 seconds, NEVER CANCEL, set timeout to 60+ minutes)
- The test suite uses pytest with pytest-anyio and pytest-httpserver plugins
- Test configuration is in `pyproject.toml` with `--doctest-modules` enabled

### Running Examples
- Run any example: `uv run python examples/<example>.py`
- **PREREQUISITE**: Requires Ollama server to be installed and running locally
- Examples include: chat, generate, tools, multimodal, structured outputs, etc.
- Test basic functionality: `uv run python examples/list.py` (lists available models)

## Validation

### Manual Testing Scenarios
- **ALWAYS** test import after making code changes: `uv run python -c "import ollama; print('Import successful')"`
- **CRITICAL LIMITATION**: Currently fails due to indentation errors in `ollama/_client.py`
- When fixed, validate basic functionality by running examples that don't require models
- Test API functionality by starting with simple examples like `examples/list.py`

### Build Validation
- **ALWAYS** run build validation: `uv build` (must complete successfully)
- **ALWAYS** run lock file check: `uv lock --check` (must pass)
- Verify no syntax errors: `uv run python -m py_compile ollama/*.py`

### CI Requirements
- The GitHub Actions workflow runs on push/PR: `.github/workflows/test.yaml`
- **CRITICAL**: Must pass `uvx hatch fmt --check -f` (formatting check)
- **CRITICAL**: Must pass `uvx hatch fmt --check -l --output-format=github` (linting)
- **CRITICAL**: Must pass `uv lock --check` (dependency lock validation)
- **CRITICAL**: Must pass `uvx hatch test -acp` (test suite - currently broken)

## Common Tasks

### Project Structure
```
.
├── ollama/                 # Main library code
│   ├── __init__.py        # Public API exports
│   ├── _client.py         # Core client implementation (HAS SYNTAX ERRORS)
│   ├── _types.py          # Pydantic data models
│   ├── _utils.py          # Utility functions
│   ├── _auth.py           # Authentication handling
│   └── _signing.py        # Request signing for ollama.com
├── tests/                 # Test suite (pytest-based)
│   ├── test_client.py     # Client functionality tests
│   ├── test_utils.py      # Utility function tests
│   └── test_type_serialization.py  # Type serialization tests
├── examples/              # 30 usage examples
├── pyproject.toml         # Project configuration (hatch + ruff)
├── uv.lock               # Dependency lockfile
└── requirements.txt       # Exported dependencies
```

### Key Dependencies
- `httpx>=0.27` - HTTP client for API calls
- `pydantic>=2.9` - Data validation and serialization
- Development tools: `pytest`, `pytest-anyio`, `pytest-httpserver`, `ruff`

### API Overview
The library provides both sync and async clients:
- `ollama.chat()` - Chat with models
- `ollama.generate()` - Generate text
- `ollama.list()` - List available models
- `ollama.pull()` - Download models
- `ollama.embed()` - Generate embeddings
- `ollama.show()` - Show model details
- `ollama.create()` - Create custom models
- `ollama.copy()` - Copy models
- `ollama.delete()` - Delete models
- `ollama.ps()` - Show running models

### Example Usage
```python
from ollama import chat
response = chat(model='gemma3', messages=[{'role': 'user', 'content': 'Hello'}])
print(response['message']['content'])
```

## Known Issues and Workarounds

### Current Syntax Errors
- **CRITICAL ISSUE**: `ollama/_client.py` has indentation errors preventing imports
- The `@overload` decorators and method definitions are incorrectly indented
- **WORKAROUND**: Cannot run tests or import the library until fixed
- **DO NOT** attempt to fix syntax issues unless specifically asked

### Testing Limitations
- Cannot run test suite due to import failures
- When fixed, expect test runtime of 10-30 seconds with proper timeout settings
- Some tests may require network access or mock servers

### CI Build Status
- Formatting and linting checks will fail due to syntax errors
- Lock file and export checks work correctly
- Build process succeeds despite syntax issues

## Timeouts and Performance

### Command Timing Expectations
- `uv sync`: ~2 seconds (first time), <1 second (subsequent)
- `uv build`: ~1 second (NEVER CANCEL, set timeout 60+ minutes)
- `uvx hatch fmt --check`: ~1 second (NEVER CANCEL, set timeout 30+ minutes)
- `uv lock --check`: <1 second
- `uv export`: <1 second
- `uvx hatch test`: Unknown due to syntax errors (estimated 10-30 seconds when working)

### Critical Timeout Settings
- **NEVER CANCEL**: All hatch operations should have 30+ minute timeouts
- **NEVER CANCEL**: Build operations should have 60+ minute timeouts
- **NEVER CANCEL**: Test operations should have 60+ minute timeouts when working

## Development Workflow

### Making Changes
1. **ALWAYS** run `uv sync` first to ensure dependencies are current
2. Make your code changes
3. **ALWAYS** test import: `uv run python -c "import ollama"`
4. **ALWAYS** run formatting: `uvx hatch fmt` 
5. **ALWAYS** run lint check: `uvx hatch fmt --check -l`
6. **ALWAYS** run build: `uv build`
7. **ALWAYS** test with examples if possible
8. When tests work: `uvx hatch test`

### Adding Dependencies
- Add runtime dependency: `uv add <package>`
- Add dev dependency: `uv add <package> --dev`
- **ALWAYS** run `uv lock --check` after changes
- **ALWAYS** run `uv export > requirements.txt` after changes

### Release Process
- Uses GitHub Actions: `.github/workflows/publish.yaml`
- Triggered on GitHub releases
- Builds with `uv build` and publishes to PyPI
- Uses trusted publishing (no manual credentials)

## External Dependencies

### Ollama Server Requirement
- **CRITICAL**: All functional testing requires Ollama server running locally
- Install from: https://ollama.com/download
- Start server: `ollama serve` (runs on http://localhost:11434)
- Pull a model for testing: `ollama pull gemma3`
- Verify server: `curl http://localhost:11434/api/version`

### Network Access
- Examples and tests may require internet access for model downloads
- Authentication tests require connection to ollama.com
- Some tests use mock HTTP servers to avoid external dependencies

## Security Considerations
- Library supports signing requests to ollama.com using Ed25519 keys
- Default key location: `~/.ollama/id_ed25519`
- Requires `cryptography` package for signing functionality
- See `SECURITY.md` for vulnerability reporting process