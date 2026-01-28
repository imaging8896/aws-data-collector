# Discord 訊號通知 - 架構更新說明

## 變更摘要

已將通知邏輯從 `aggregate_daily_stats` Lambda 分離出來，改為獨立的定時任務。

## 新架構

### Lambda 函數

1. **aggregate_daily_stats** - 資料聚合
   - 執行頻率：每 3 小時
   - 功能：
     - 聚合新聞統計
     - 計算 RSI、MA 指標
     - 執行策略檢測
     - 儲存結果到 DynamoDB
   - **不再負責發送通知**

2. **check_trading_signals** - 訊號檢查與通知 ⭐ 新增
   - 執行頻率：**每日早上 8:00**
   - 功能：
     - 讀取 DynamoDB 最新 daily stats
     - 檢查所有結尾是「類」的指數
     - 找出買入/賣出訊號（中線、短線）
     - 使用 AI 查詢代表性股票
     - 發送 Discord 通知
     - 防止重複通知（20 小時內）

3. **notify_discord** - Discord 發送
   - 執行頻率：按需（由 check_trading_signals 調用）
   - 功能：發送 Discord webhook

## 優勢

### 1. **解耦合**
- 統計聚合與通知邏輯分離
- 各自獨立運作，互不影響

### 2. **更可控**
- 明確的通知時間（每天早上 8 點）
- 可獨立測試和調整

### 3. **更靈活**
- 可隨時手動觸發檢查
- 可輕鬆調整通知時間

### 4. **成本優化**
- check_trading_signals 每天只執行一次
- 使用 Parameter Store（免費）而非 Secrets Manager

## 執行流程

```
┌─────────────────────────────────────────┐
│  EventBridge (每 3 小時)                 │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  aggregate_daily_stats                   │
│  - 聚合新聞統計                           │
│  - 計算 RSI/MA                           │
│  - 執行策略檢測                           │
│  - 儲存到 DynamoDB                       │
└─────────────────────────────────────────┘

═══════════════════════════════════════════

┌─────────────────────────────────────────┐
│  EventBridge (每日 8:00 AM)              │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  check_trading_signals                   │
│  - 讀取最新 stats                         │
│  - 檢查「類」指數訊號                      │
│  - AI 找代表性股票                        │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  notify_discord                          │
│  - 格式化訊息                             │
│  - 發送 Discord webhook                  │
└─────────────────────────────────────────┘
```

## 新增文件

- `lambda/check_trading_signals/main.py` - 訊號檢查主程式
- `lambda/check_trading_signals/requirements.txt` - 依賴（google-genai）
- `lambda_check_trading_signals.tf` - Terraform 配置

## 修改文件

- `lambda/aggregate_daily_stats/main.py` - 移除通知邏輯
- `lambda_aggregate_daily_stats.tf` - 移除 DISCORD_NOTIFY_FUNCTION_NAME

## 刪除文件

- `lambda/aggregate_daily_stats/stock_finder.py` - 移到 check_trading_signals

## 測試

### 測試訊號檢查
```bash
aws lambda invoke \
  --function-name dev-aws-data-collector-check-trading-signals \
  --payload '{}' \
  response.json

cat response.json
```

### 查看日誌
```bash
# 訊號檢查日誌
aws logs tail /aws/lambda/dev-aws-data-collector-check-trading-signals --follow

# Discord 通知日誌
aws logs tail /aws/lambda/dev-aws-data-collector-notify-discord --follow
```

## 部署

```bash
terraform apply
```

這將會：
1. 創建 check_trading_signals Lambda
2. 創建 Layer（包含 google-genai）
3. 創建 EventBridge 規則（每日 8:00 AM）
4. 更新 aggregate_daily_stats（移除通知相關配置）

## 成本

**零額外成本！**

- check_trading_signals: 每天執行 1 次（Lambda 免費額度內）
- Parameter Store: 免費
- EventBridge: 免費額度內

## 時區說明

EventBridge 使用 UTC 時間：
- `cron(0 0 * * ? *)` = 00:00 UTC = 08:00 台灣時間

如需調整時間，修改 `lambda_check_trading_signals.tf` 中的 `schedule_expression`。
