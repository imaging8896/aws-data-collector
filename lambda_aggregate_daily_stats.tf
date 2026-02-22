# ===== Aggregate Daily Stats Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_aggregate_stats_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/aggregate_daily_stats"
  output_path = "${path.module}/lambda_aggregate_stats_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Lambda Function
resource "aws_lambda_function" "aggregate_stats" {
  filename         = data.archive_file.lambda_aggregate_stats_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-aggregate-stats"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_aggregate_stats_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 256
  timeout         = 120
  architectures    = ["arm64"]

  environment {
    variables = {
      DYNAMODB_STATS_TABLE_NAME        = aws_dynamodb_table.daily_stats_table.name
      DYNAMODB_INDEX_TABLE_NAME        = aws_dynamodb_table.index_data_table.name
      DYNAMODB_INDEX_STOCKS_TABLE_NAME = aws_dynamodb_table.index_stocks_table.name
      DYNAMODB_MARKET_DATA_TABLE_NAME  = aws_dynamodb_table.market_data_table.name
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
resource "aws_cloudwatch_log_group" "lambda_aggregate_stats_logs" {
  name              = "/aws/lambda/${aws_lambda_function.aggregate_stats.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger aggregation hourly
resource "aws_cloudwatch_event_rule" "aggregate_stats_schedule" {
  name                = "${var.environment}-${var.project_name}-aggregate-stats-schedule"
  description         = "Trigger stats aggregation every 3 hours"
  schedule_expression = "rate(3 hours)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "aggregate_stats_target" {
  rule      = aws_cloudwatch_event_rule.aggregate_stats_schedule.name
  target_id = "AggregateStatsLambda"
  arn       = aws_lambda_function.aggregate_stats.arn
  
  input = jsonencode({
    days = 2
  })
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_aggregate_stats" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.aggregate_stats.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.aggregate_stats_schedule.arn
}

# Lambda Destination: Trigger static website generator on success
resource "aws_lambda_function_event_invoke_config" "aggregate_stats_destination" {
  function_name = aws_lambda_function.aggregate_stats.function_name
  
  # Disable automatic retries
  maximum_retry_attempts = 0

  destination_config {
    on_success {
      destination = aws_lambda_function.static_website_generator.arn
    }
  }
}

# Permission for aggregate_stats to invoke static_website_generator
resource "aws_lambda_permission" "aggregate_stats_invoke_static_website" {
  statement_id  = "AllowExecutionFromAggregateStats"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.static_website_generator.function_name
  principal     = "lambda.amazonaws.com"
  source_arn    = aws_lambda_function.aggregate_stats.arn
}
