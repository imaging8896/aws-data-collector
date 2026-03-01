# ===== Fetch Index Stocks Data Lambda =====
# This Lambda fetches market data for all stocks in the index_stocks_table
# Triggered daily to collect price data sufficient for RSI calculation
# Batches stocks into groups of 20 for fetch_market_data

# Lambda function source code archive
data "archive_file" "lambda_fetch_index_stocks_data_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/fetch_index_stocks_data"
  output_path = "${path.module}/lambda_fetch_index_stocks_data_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Lambda Function
resource "aws_lambda_function" "fetch_index_stocks_data" {
  filename         = data.archive_file.lambda_fetch_index_stocks_data_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-fetch-index-stocks-data"
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.handler"
  source_code_hash = data.archive_file.lambda_fetch_index_stocks_data_zip.output_base64sha256
  runtime          = var.lambda_runtime
  memory_size      = 128
  timeout          = 120
  architectures    = ["arm64"]

  environment {
    variables = {
      DYNAMODB_INDEX_STOCKS_TABLE_NAME = aws_dynamodb_table.index_stocks_table.name
      FETCH_MARKET_DATA_FUNCTION_NAME  = aws_lambda_function.fetch_market_data.function_name
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
resource "aws_cloudwatch_log_group" "lambda_fetch_index_stocks_data_logs" {
  name              = "/aws/lambda/${aws_lambda_function.fetch_index_stocks_data.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger daily at 16:05 Taiwan time (08:05 UTC)
# 5 minutes after fetch_market_data to ensure index data is available
resource "aws_cloudwatch_event_rule" "fetch_index_stocks_data_schedule" {
  name                = "${var.environment}-${var.project_name}-fetch-index-stocks-data-schedule"
  description         = "Trigger index stocks data fetch daily at 16:05 Taiwan time"
  schedule_expression = "cron(5 8 * * ? *)" # 08:05 UTC = 16:05 Taiwan (UTC+8)

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "fetch_index_stocks_data_target" {
  rule      = aws_cloudwatch_event_rule.fetch_index_stocks_data_schedule.name
  target_id = "FetchIndexStocksDataLambda"
  arn       = aws_lambda_function.fetch_index_stocks_data.arn

  input = jsonencode({
    period = "1y" # Fetch 1 year of data using yfinance
  })
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_fetch_index_stocks_data" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fetch_index_stocks_data.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.fetch_index_stocks_data_schedule.arn
}
