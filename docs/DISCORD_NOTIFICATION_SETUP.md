# Discord 交易訊號通知功能

## 功能說明

此功能會在每日 aggregate 統計完成後，自動檢測結尾是「類」的指數（如金融類、半導體類等），當發現中線或短線買入訊號時：

1. **訊號檢測**：
   - **中線策略**：20MA > 60MA 且收盤價 > 20MA 且 5日 RSI < 45
   - **短線策略**：突破 3 日高點 且漲幅 > 1% 且 RSI 在 50-65 且量能放大

2. **AI 股票查詢**：使用 Gemini AI 找出該指數最具代表性的 5 家上市公司

3. **Discord 通知**：透過 Webhook 發送精美的嵌入訊息，包含：
   - 指數名稱
   - 訊號類型（中線/短線）
   - 代表性股票代號和名稱
   - 時間戳記

4. **每日一次**：系統會記錄最後通知時間，確保每個日期只通知一次（20 小時內不重複）

## 架構組件

### Lambda 函數

1. **aggregate_daily_stats**
   - 負責每 3 小時聚合新聞統計
   - 計算 RSI、MA 指標
   - 執行中線和短線策略檢測
   - 儲存結果到 DynamoDB

2. **check_trading_signals**（新建）
   - 每日早上 8:00 執行
   - 讀取 DynamoDB 中最新的 daily stats
   - 檢查結尾是「類」的指數訊號
   - 使用 AI 查詢代表性股票
   - 調用 Discord 通知 Lambda

3. **notify_discord**
   - 接收訊號資訊
   - 格式化 Discord 訊息
   - 發送 Webhook 請求

### 相關文件

- `lambda/aggregate_daily_stats/main.py` - 主要聚合邏輯和 RSI 計算
- `lambda/aggregate_daily_stats/strategy/medium.py` - 中線策略
- `lambda/aggregate_daily_stats/strategy/short.py` - 短線策略
- `lambda/check_trading_signals/main.py` - 每日訊號檢查和通知
- `lambda/notify_discord/main.py` - Discord 通知處理
- `lambda_check_trading_signals.tf` - 訊號檢查 Lambda Terraform 配置
- `lambda_notify_discord.tf` - Discord Lambda 配置
- `lambda_aggregate_daily_stats.tf` - Aggregate Lambda 配置

## 設定步驟

### 1. 建立 Discord Webhook

1. 進入你的 Discord 伺服器
2. 點擊「伺服器設定」>「整合」>「Webhooks」
3. 點擊「新建 Webhook」
4. 設定名稱和頻道
5. 複製 Webhook URL

### 2. 配置 Terraform 變數

編輯 `terraform.tfvars` 文件（或使用 `terraform.tfvars.example` 作為模板）：

```hcl
# Discord webhook URL for trading signal notifications
discord_webhook_url = "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

### 3. 部署基礎設施

```bash
# 初始化 Terraform（如果還沒做過）
terraform init

# 預覽變更
terraform plan

# 應用變更
terraform apply
```

### 4. 測試功能

你可以手動觸發 check_trading_signals Lambda 來測試：

```bash
aws lambda invoke \
  --function-name dev-aws-data-collector-check-trading-signals \
  --payload '{}' \
  response.json

cat response.json
```

## 訊息範例

Discord 通知訊息會包含：

```
🟢 金融類 - 中線買入訊號

偵測到 金融類 出現中線買入訊號

📊 代表性股票
• 2330 (台積電)
• 2317 (鴻海)
• 2454 (聯發科)
• 2882 (國泰金)
• 2412 (中華電)

📅 時間: 2026-01-27 14:30
📈 策略類型: 中線

AWS Data Collector - 每日一次通知
```

## 成本估算

- **Lambda 執行**：
  - aggregate_daily_stats: 每 3 小時執行一次（每日 8 次），增加約 1-2 秒處理訊號檢測
  - notify_discord: 僅在有訊號時執行（預估每日 0-5 次）
  - 估計每月成本：< $0.01（Lambda 免費額度內）

- **Parameter Store**：
  - 標準參數（小於 4KB）完全免費
  - 成本：$0.00/月

- **Lambda 調用**：
  - aggregate_daily_stats 調用 notify_discord（異步）
  - 無額外費用（Lambda 免費額度內）

**總增加成本：完全免費！** ✅

## 停用通知

如果不想使用 Discord 通知功能，可以：

1. 在 `terraform.tfvars` 中將 `discord_webhook_url` 設為空字串
2. 重新 apply：`terraform apply`

系統會自動檢測並跳過通知邏輯。

## 疑難排解

### 沒有收到通知

1. 檢查 CloudWatch Logs：
   ```bash
   aws logs tail /aws/lambda/dev-aws-data-collector-aggregate-stats --follow
   ```

2. 確認訊號檢測邏輯：
   - 查看 DynamoDB daily_stats_table 中的 RSI 數據
   - 確認是否有指數滿足買入條件

3. 測試 Discord Webhook：
   ```bash
   curl -X POST YOUR_WEBHOOK_URL \
     -H "Content-Type: application/json" \
     -d '{"content": "Test message"}'
   ```

### 重複通知

系統會在 DynamoDB 中記錄 `last_notification_timestamp`，20 小時內不會重複通知。如果需要重置：

```bash
aws dynamodb update-item \
  --table-name dev-aws-data-collector-daily-stats \
  --key '{"date": {"S": "2026-01-27"}}' \
  --update-expression "REMOVE last_notification_timestamp"
```

## 自訂功能

### 修改策略條件

編輯策略文件：
- 中線：`lambda/aggregate_daily_stats/strategy/medium.py`
- 短線：`lambda/aggregate_daily_stats/strategy/short.py`

### 修改通知格式

編輯 `lambda/notify_discord/main.py` 中的 `send_discord_notification` 函數。

### 調整 AI 股票數量

編輯 `lambda/aggregate_daily_stats/stock_finder.py` 中的提示詞，修改回傳股票數量。
