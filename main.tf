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
