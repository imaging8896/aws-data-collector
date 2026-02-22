## MyPy Type Checking

### Installation
1. Install MyPy via pip:
   ```bash
   pip install mypy
   ```

### Configuration
2. Create a `mypy.ini` file in the root of your project with the following content:
   ```ini
   [mypy]
   files = .
   ```

### Type Hint Requirements for Lambda Functions
3. Use type hints in your Lambda function signatures. For example:
   ```python
   def lambda_handler(event: dict, context: Any) -> str:
       return "Hello, World!"
   ```
4. Ensure all parameters and return types in your functions are properly annotated.