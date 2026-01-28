# ===== Discord Notification Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_notify_discord_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/notify_discord"
  output_path = "${path.module}/lambda_notify_discord_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Lambda Function
resource "aws_lambda_function" "notify_discord" {
  filename         = data.archive_file.lambda_notify_discord_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-notify-discord"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_notify_discord_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 128
  timeout         = 30
  architectures    = ["arm64"]

  environment {
    variables = {
      DISCORD_WEBHOOK_PARAMETER_NAME = aws_ssm_parameter.discord_webhook_url.name
      ENVIRONMENT                    = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_notify_discord_logs" {
  name              = "/aws/lambda/${aws_lambda_function.notify_discord.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# IAM Policy for Discord Lambda to access Parameter Store
resource "aws_iam_role_policy" "lambda_notify_discord_ssm_policy" {
  name = "${var.environment}-${var.project_name}-notify-discord-ssm-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = aws_ssm_parameter.discord_webhook_url.arn
      }
    ]
  })
}
