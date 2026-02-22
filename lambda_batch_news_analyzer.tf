# ===== Batch News Analyzer Lambda =====

# Lambda function source code archive
data "archive_file" "batch_analyzer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/batch_news_analyzer"
  output_path = "${path.module}/lambda_batch_analyzer_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Create Lambda Layer with dependencies
resource "terraform_data" "install_batch_analyzer_dependencies" {
  triggers_replace = {
    requirements = filemd5("${path.module}/lambda/batch_news_analyzer/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_batch_analyzer || true
      mkdir -p ${path.module}/layer_batch_analyzer/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/lambda/batch_news_analyzer/requirements.txt:/tmp/requirements.txt" \
        -v "$(pwd)/${path.module}/layer_batch_analyzer/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install -r /tmp/requirements.txt -t /var/task --upgrade
      cd ${path.module}/layer_batch_analyzer && zip -r ../lambda_batch_analyzer_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "batch_analyzer_layer" {
  filename                 = "${path.module}/lambda_batch_analyzer_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-batch-analyzer"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_batch_analyzer_dependencies.id

  depends_on = [terraform_data.install_batch_analyzer_dependencies]
}

# Lambda Function
resource "aws_lambda_function" "batch_news_analyzer" {
  filename         = data.archive_file.batch_analyzer_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-batch-analyzer"
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.handler"
  source_code_hash = data.archive_file.batch_analyzer_zip.output_base64sha256
  runtime          = var.lambda_runtime
  memory_size      = 128
  timeout          = 60
  architectures    = ["arm64"]
  layers           = [aws_lambda_layer_version.batch_analyzer_layer.arn]

  environment {
    variables = {
      DYNAMODB_TABLE_NAME        = aws_dynamodb_table.news_urls_table.name
      DYNAMODB_BATCH_TABLE_NAME  = aws_dynamodb_table.batch_requests_table.name
      GEMINI_API_KEY_SECRET_NAME = aws_secretsmanager_secret.gemini_api_key.name
      CATEGORIES                 = var.categories
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "batch_analyzer_logs" {
  name              = "/aws/lambda/${aws_lambda_function.batch_news_analyzer.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge Rule to trigger every 1 hour
resource "aws_cloudwatch_event_rule" "batch_analyzer_schedule" {
  name                = "${var.environment}-${var.project_name}-batch-analyzer-schedule"
  description         = "Trigger batch news analyzer every 1 hour"
  schedule_expression = "rate(1 hour)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "batch_analyzer_target" {
  rule      = aws_cloudwatch_event_rule.batch_analyzer_schedule.name
  target_id = "BatchAnalyzerLambda"
  arn       = aws_lambda_function.batch_news_analyzer.arn

  depends_on = [aws_cloudwatch_event_rule.batch_analyzer_schedule]
}

# Lambda Permission for EventBridge to invoke
resource "aws_lambda_permission" "batch_analyzer_eventbridge_invoke" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.batch_news_analyzer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.batch_analyzer_schedule.arn
}

# IAM Policy for Lambda to access Gemini API secrets
resource "aws_iam_policy" "batch_analyzer_secrets_policy" {
  name        = "${var.environment}-${var.project_name}-batch-analyzer-secrets-policy"
  description = "Allow Lambda to access Gemini API secret"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.gemini_api_key.arn
      }
    ]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Attach secrets policy to Lambda role
resource "aws_iam_role_policy_attachment" "batch_analyzer_secrets_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.batch_analyzer_secrets_policy.arn
}
