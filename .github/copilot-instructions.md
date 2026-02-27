## Human-Reviewable Code Requirements

生成的程式碼必須容易被人類審閱 (code review)。請遵循以下原則：

### 命名規範 (Naming Conventions)

- 使用有意義且描述性的變數名稱、函式名稱和類別名稱
- 避免使用單字母變數（除了迴圈計數器如 `i`, `j`）
- 函式名稱應清楚表達其功能，例如 `calculate_daily_average` 而非 `calc`

### 程式碼結構 (Code Structure)

- 每個函式應只做一件事（Single Responsibility Principle）
- 函式長度建議不超過 50 行，超過時應考慮拆分
- 避免深層巢狀（建議最多 3 層縮排）
- 相關的程式碼應放在一起，並用空行分隔不同邏輯區塊

### 註解與文件 (Comments and Documentation)

- 為複雜的商業邏輯加上註解說明「為什麼」這樣做
- 使用 docstring 描述函式的用途、參數和回傳值
- 避免無意義的註解，如 `# increment i by 1`

### 錯誤處理 (Error Handling)

- 使用明確的錯誤訊息，讓 reviewer 容易理解錯誤情境
- Python：避免空的 except 區塊，應明確指定要捕捉的例外類型
- Terraform：善用 `validation` 區塊驗證變數輸入，並提供清楚的錯誤訊息

### 程式碼一致性 (Code Consistency)

- 遵循專案既有的程式碼風格
- 使用一致的縮排和格式（由 Ruff 和 Terraform fmt 自動處理）

### 外部資料調用規則 (External Data Fetching Requirements)

**重要**: 當需要從外部網址（網頁或 API）取得資料時，必須遵循以下步驟：

1. **實際呼叫並驗證**: 在產生程式碼前，務必實際呼叫該網址/API 並取得真實的資料格式
2. **文件化資料結構**: 清楚記錄接收到的資料格式、欄位名稱、資料型別和結構
3. **基於真實資料產生**: 根據實際取得的資料格式編寫程式碼，避免基於假設或猜測生成代碼
4. **錯誤處理**: 考慮可能的響應變化和邊界情況，加入適當的錯誤處理機制

---

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
tf fmt -recursive
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
tf fmt -check -recursive && tflint && checkov -d . --framework terraform --quiet
```
