# Discord 訊號通知 - 快速部署指南

## 一分鐘設定

### 1. 取得 Discord Webhook URL
1. Discord 伺服器 → 設定 → 整合 → Webhooks
2. 新建 Webhook → 複製 URL

### 2. 配置 terraform.tfvars
```hcl
discord_webhook_url = "https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
```

### 3. 部署
```bash
terraform apply
```

## 功能說明

✅ 每日早上 8:00 自動檢查 DynamoDB 最新資料  
✅ 自動檢測「XX類」指數的買入/賣出訊號  
✅ AI 找出代表性股票（前 5 名）  
✅ Discord 精美通知  
✅ 每日一次，不重複

## 觸發條件

**中線**：20MA > 60MA + 價格 > 20MA + RSI5 < 45  
**短線**：突破 3 日高 + 漲幅 > 1% + RSI 50-65 + 量增

## 成本
完全免費！✨  
（使用 AWS Parameter Store 標準參數）

詳細文件：[DISCORD_NOTIFICATION_SETUP.md](./DISCORD_NOTIFICATION_SETUP.md)
