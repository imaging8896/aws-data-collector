## Code Quality Checks

Before committing code, always run the following checks:

### Ruff (Linter and Formatter)

```bash
# Install ruff
pip install ruff

# Run linter with auto-fix
ruff check --fix lambda/

# Run formatter
ruff format lambda/
```

### MyPy (Type Checking)

MyPy: 強制型別檢查。AI 在有 Type Hints 的環境下生成的程式碼準確度更高。

```bash
# Install mypy
pip install mypy

# Run type checking (uses mypy.ini configuration)
mypy
```

### Type Hint Requirements for Lambda Functions

Use type hints in your Lambda function signatures. For example:
```python
def lambda_handler(event: dict, context: Any) -> str:
    return "Hello, World!"
```

Ensure all parameters and return types in your functions are properly annotated.