# Main infrastructure components are separated into different files:
# - dynamodb.tf: DynamoDB tables
# - iam.tf: IAM roles and policies
# - lambda_get_news_urls.tf: Lambda for collecting news URLs
# - lambda_get_news_content.tf: Lambda for collecting news content

# Secrets Manager for OpenAI API Key
resource "aws_secretsmanager_secret" "openai_api_key" {
  name        = "${var.environment}/${var.project_name}/openai-api-key"
  description = "OpenAI API key for news analysis"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}
