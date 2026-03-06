# ===== Check Panic Signal Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_check_panic_signal_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/check_panic_signal"
  output_path = "${path.module}/lambda_check_panic_signal_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Lambda Function
resource "aws_lambda_function" "check_panic_signal" {
  filename         = data.archive_file.lambda_check_panic_signal_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-check-panic-signal"
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.handler"
  source_code_hash = data.archive_file.lambda_check_panic_signal_zip.output_base64sha256
  runtime          = var.lambda_runtime
  memory_size      = 256
  timeout          = 120
  architectures    = ["arm64"]

  environment {
    variables = {
      MARKET_DATA_TABLE_NAME       = aws_dynamodb_table.market_data_table.name
      MARKET_STATS_TABLE_NAME      = aws_dynamodb_table.market_stats_table.name
      DISCORD_NOTIFY_FUNCTION_NAME = aws_lambda_function.notify_discord.function_name
      ENVIRONMENT                  = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_check_panic_signal_logs" {
  name              = "/aws/lambda/${aws_lambda_function.check_panic_signal.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger check at 8:30 AM Taiwan time daily (00:30 UTC)
resource "aws_cloudwatch_event_rule" "check_panic_signal_schedule" {
  name                = "${var.environment}-${var.project_name}-check-panic-signal-schedule"
  description         = "Trigger panic signal check daily at 8:30 AM Taiwan time"
  schedule_expression = "cron(30 0 * * ? *)" # 8:30 AM Taiwan = 00:30 UTC

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "check_panic_signal_target" {
  rule      = aws_cloudwatch_event_rule.check_panic_signal_schedule.name
  target_id = "CheckPanicSignalLambda"
  arn       = aws_lambda_function.check_panic_signal.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_check_panic_signal" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.check_panic_signal.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.check_panic_signal_schedule.arn
}
