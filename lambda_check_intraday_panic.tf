# ===== Check Intraday Panic Lambda =====
# Checks for ultimate exhaustion panic buy signal at 13:15 Taiwan time

# Lambda function source code archive
data "archive_file" "lambda_check_intraday_panic_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/check_intraday_panic"
  output_path = "${path.module}/lambda_check_intraday_panic_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Lambda Function
resource "aws_lambda_function" "check_intraday_panic" {
  filename         = data.archive_file.lambda_check_intraday_panic_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-check-intraday-panic"
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.handler"
  source_code_hash = data.archive_file.lambda_check_intraday_panic_zip.output_base64sha256
  runtime          = var.lambda_runtime
  memory_size      = 256
  timeout          = 120
  architectures    = ["arm64"]

  layers = [
    aws_lambda_layer_version.fetch_market_data_dependencies_layer.arn,
    aws_lambda_layer_version.panic_common_layer.arn,
  ]

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
resource "aws_cloudwatch_log_group" "lambda_check_intraday_panic_logs" {
  name              = "/aws/lambda/${aws_lambda_function.check_intraday_panic.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger at 13:15 Taiwan time on weekdays (05:15 UTC)
# Taiwan market trading hours: 9:00 - 13:30
resource "aws_cloudwatch_event_rule" "check_intraday_panic_schedule" {
  name                = "${var.environment}-${var.project_name}-check-intraday-panic-schedule"
  description         = "Trigger intraday panic check at 13:15 Taiwan time on weekdays"
  schedule_expression = "cron(15 5 ? * MON-FRI *)" # 13:15 Taiwan = 05:15 UTC

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "check_intraday_panic_target" {
  rule      = aws_cloudwatch_event_rule.check_intraday_panic_schedule.name
  target_id = "CheckIntradayPanicLambda"
  arn       = aws_lambda_function.check_intraday_panic.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_check_intraday_panic" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.check_intraday_panic.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.check_intraday_panic_schedule.arn
}
