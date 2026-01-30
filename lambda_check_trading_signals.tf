# ===== Check Trading Signals Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_check_trading_signals_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/check_trading_signals"
  output_path = "${path.module}/lambda_check_trading_signals_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Lambda Function
resource "aws_lambda_function" "check_trading_signals" {
  filename         = data.archive_file.lambda_check_trading_signals_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-check-trading-signals"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_check_trading_signals_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 256
  timeout         = 300
  architectures    = ["arm64"]

  environment {
    variables = {
      DYNAMODB_STATS_TABLE_NAME        = aws_dynamodb_table.daily_stats_table.name
      DYNAMODB_INDEX_STOCKS_TABLE_NAME = aws_dynamodb_table.index_stocks_table.name
      DISCORD_NOTIFY_FUNCTION_NAME     = aws_lambda_function.notify_discord.function_name
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
resource "aws_cloudwatch_log_group" "lambda_check_trading_signals_logs" {
  name              = "/aws/lambda/${aws_lambda_function.check_trading_signals.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger check at 8:00 AM daily (UTC+8 = 00:00 UTC)
resource "aws_cloudwatch_event_rule" "check_signals_schedule" {
  name                = "${var.environment}-${var.project_name}-check-signals-schedule"
  description         = "Trigger trading signals check daily at 8:00 AM Taiwan time"
  schedule_expression = "cron(0 0 * * ? *)"  # 8:00 AM Taiwan = 00:00 UTC

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "check_signals_target" {
  rule      = aws_cloudwatch_event_rule.check_signals_schedule.name
  target_id = "CheckTradingSignalsLambda"
  arn       = aws_lambda_function.check_trading_signals.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_check_signals" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.check_trading_signals.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.check_signals_schedule.arn
}
