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

---

## Terraform AI 反向審查 (AI Reverse Review)

**重要**: 當修改任何 Terraform 檔案 (`*.tf`, `*.tfvars`) 後，**必須**執行以下反向審查流程：

### 審查流程

1. **執行 Terraform Plan**
   ```bash
   # 初始化 (如果尚未初始化)
   # 注意: 使用 -backend=false 時無法比較遠端狀態
   # 若需要完整的狀態比較，請確保已配置正確的 backend
   terraform init -backend=false
   
   # 執行 plan 並儲存輸出
   terraform plan -no-color 2>&1 | tee /tmp/terraform_plan_output.txt
   ```

2. **AI 自我審查 Plan 結果**
   
   在執行 `terraform plan` 後，請仔細審查輸出並產生審查報告，包含以下項目：

   #### 審查項目清單

   | 類別 | 檢查項目 | 風險等級 |
   |------|----------|----------|
   | **變更摘要** | 列出所有要新增、修改、刪除的資源 | - |
   | **資安風險** | 是否有公開的 S3 bucket、過於寬鬆的 IAM Policy、未加密的資源 | 🔴 高 |
   | **成本影響** | 是否有高成本資源 (如 NAT Gateway, RDS, EKS) | 🟡 中 |
   | **破壞性變更** | 是否有 `destroy` 或 `replace` 的資源 | 🔴 高 |
   | **最佳實踐** | 是否符合 AWS Well-Architected Framework | 🟢 低 |
   | **相依性風險** | 是否有跨資源相依性可能導致服務中斷 | 🟡 中 |

   #### 審查報告格式

   請以以下格式產生審查報告：

   ```markdown
   ## 🔍 Terraform Plan AI 審查報告

   ### 📋 變更摘要
   - **新增**: X 個資源
   - **修改**: X 個資源  
   - **刪除**: X 個資源

   ### 🔴 高風險項目
   - [列出發現的高風險問題]

   ### 🟡 中風險項目
   - [列出發現的中風險問題]

   ### 🟢 低風險項目 / 建議
   - [列出發現的低風險問題或改善建議]

   ### ✅ 審查結論
   - [ ] 建議：可以安全 apply
   - [ ] 警告：需要人工確認後再 apply
   - [ ] 拒絕：存在嚴重問題，不建議 apply
   ```

3. **將審查報告輸出至檔案**
   
   將審查報告儲存至 `/tmp/terraform_review_report.md`，並在對話中顯示報告內容。

### 自動觸發條件

以下情況會自動觸發 AI 反向審查：
- 新增 `.tf` 檔案
- 修改現有 `.tf` 檔案
- 修改 `.tfvars` 檔案
- 修改 `terraform.tfvars` 或任何變數檔案

### 審查重點提醒

1. **資源刪除警告**: 如果 plan 顯示要刪除資源，務必確認是否為預期行為
2. **敏感資料暴露**: 檢查是否有 API key、密碼等敏感資訊被硬編碼
3. **權限過大**: 檢查 IAM Policy 是否使用 `*` 萬用字元
4. **公開存取**: 檢查是否有資源被設定為公開存取
5. **加密設定**: 確認所有資料儲存服務都啟用加密
