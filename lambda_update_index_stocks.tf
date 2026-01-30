# ===== Update Index Stocks Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_update_index_stocks_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/update_index_stocks"
  output_path = "${path.module}/lambda_update_index_stocks_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Create Lambda Layer with google-genai dependency
resource "terraform_data" "install_update_index_stocks_dependencies" {
  triggers_replace = {
    version = "1"
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_update_index_stocks || true
      mkdir -p ${path.module}/layer_update_index_stocks/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/layer_update_index_stocks/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install google-genai -t /var/task --upgrade
      cd ${path.module}/layer_update_index_stocks && zip -r ../lambda_update_index_stocks_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "update_index_stocks_dependencies_layer" {
  filename                 = "${path.module}/lambda_update_index_stocks_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-update-index-stocks-dependencies"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_update_index_stocks_dependencies.id

  depends_on = [terraform_data.install_update_index_stocks_dependencies]
}

# Lambda Function
resource "aws_lambda_function" "update_index_stocks" {
  filename         = data.archive_file.lambda_update_index_stocks_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-update-index-stocks"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_update_index_stocks_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 256
  timeout         = 300  # 5 minutes to process all indexes
  architectures    = ["arm64"]
  layers           = [aws_lambda_layer_version.update_index_stocks_dependencies_layer.arn]

  environment {
    variables = {
      DYNAMODB_INDEX_STOCKS_TABLE_NAME = aws_dynamodb_table.index_stocks_table.name
      DYNAMODB_STATS_TABLE_NAME        = aws_dynamodb_table.daily_stats_table.name
      GEMINI_API_KEY_SECRET_NAME       = aws_secretsmanager_secret.gemini_api_key.name
      ENVIRONMENT                      = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_update_index_stocks_logs" {
  name              = "/aws/lambda/${aws_lambda_function.update_index_stocks.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger monthly on the 1st at 00:00 UTC (8:00 AM Taiwan)
resource "aws_cloudwatch_event_rule" "update_index_stocks_schedule" {
  name                = "${var.environment}-${var.project_name}-update-index-stocks-schedule"
  description         = "Update representative stocks for indexes monthly on the 1st"
  schedule_expression = "cron(0 0 1 * ? *)"  # 1st day of month at 00:00 UTC (8:00 AM Taiwan)

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "update_index_stocks_target" {
  rule      = aws_cloudwatch_event_rule.update_index_stocks_schedule.name
  target_id = "UpdateIndexStocksLambda"
  arn       = aws_lambda_function.update_index_stocks.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_update_index_stocks" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.update_index_stocks.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.update_index_stocks_schedule.arn
}
