# Main infrastructure components are separated into different files:
# - dynamodb.tf: DynamoDB tables
# - iam.tf: IAM roles and policies
# - lambda_get_news_urls.tf: Lambda for collecting news URLs
# - lambda_get_news_content.tf: Lambda for collecting news content

# Secrets Manager for Gemini API Key
resource "aws_secretsmanager_secret" "gemini_api_key" {
  name        = "${var.environment}/${var.project_name}/gemini-api-key"
  description = "Google Gemini API key for news analysis"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_secretsmanager_secret_version" "gemini_api_key" {
  secret_id     = aws_secretsmanager_secret.gemini_api_key.id
  secret_string = var.gemini_api_key
}

# Parameter Store for Discord Webhook URL (free tier, cost-optimized)
resource "aws_ssm_parameter" "discord_webhook_url" {
  name        = "/${var.environment}/${var.project_name}/discord-webhook-url"
  description = "Discord webhook URL for trading signal notifications"
  type        = "SecureString" # Encrypted at rest
  value       = var.discord_webhook_url

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
