## Code Quality Checks

Before committing code, always run the following checks:

### Python Code Quality (for Lambda functions)

#### Ruff (Linter and Formatter)

```bash
# Install ruff
pip install ruff

# Run linter with auto-fix
ruff check --fix lambda/

# Run formatter
ruff format lambda/
```

#### MyPy (Type Checking)

MyPy: 強制型別檢查。AI 在有 Type Hints 的環境下生成的程式碼準確度更高。

```bash
# Install mypy
pip install mypy

# Run type checking (uses mypy.ini configuration)
mypy
```

#### Type Hint Requirements for Lambda Functions

Use type hints in your Lambda function signatures. For example:
```python
def lambda_handler(event: dict, context: Any) -> str:
    return "Hello, World!"
```

Ensure all parameters and return types in your functions are properly annotated.

### Terraform Code Quality (for Infrastructure as Code)

在修改 Terraform 檔案 (*.tf) 之前，務必執行以下檢查以確保程式碼品質和資安合規。

#### Terraform Format (基本格式化)

```bash
# Check formatting (dry-run)
terraform fmt -check -recursive

# Auto-fix formatting
terraform fmt -recursive
```

#### TFLint (雲端服務最佳實踐檢查)

TFLint 檢查 AWS/GCP/Azure 等雲端服務的最佳實踐，例如是否遺漏必填標籤、無效的資源類型等。

```bash
# Install TFLint (macOS)
brew install tflint

# Install TFLint (Linux)
curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash

# Initialize TFLint plugins (AWS)
tflint --init

# Run TFLint
tflint
```

#### Checkov (資安風險檢查)

Checkov 是關鍵的資安檢查工具，用於檢測 AI 生成的 Terraform 是否具有資安風險，例如：S3 Public Access、未加密的資源、過於寬鬆的 IAM Policy 等。

```bash
# Install Checkov
pip install checkov

# Run Checkov on all Terraform files
checkov -d . --framework terraform

# Run Checkov with specific checks (optional)
checkov -d . --framework terraform --check CKV_AWS_18,CKV_AWS_19,CKV_AWS_21
```

#### 常見的 Checkov 資安檢查項目

- `CKV_AWS_18`: S3 bucket 是否啟用 access logging
- `CKV_AWS_19`: S3 bucket 是否啟用伺服器端加密
- `CKV_AWS_20`: S3 bucket 是否阻止公開存取
- `CKV_AWS_21`: S3 bucket 是否啟用版本控制
- `CKV_AWS_23`: 安全群組是否有描述
- `CKV_AWS_24`: 安全群組是否允許來自 0.0.0.0/0 的 SSH
- `CKV_AWS_25`: 安全群組是否允許來自 0.0.0.0/0 的 RDP

#### 執行所有 Terraform 檢查

```bash
# 一次執行所有檢查的組合指令
terraform fmt -check -recursive && tflint && checkov -d . --framework terraform --quiet
```