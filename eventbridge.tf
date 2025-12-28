# EventBridge rule to trigger trend analyzer daily at 8:50 AM Taiwan time (00:50 UTC)
resource "aws_cloudwatch_event_rule" "daily_trend_analysis" {
  name                = "${var.environment}-${var.project_name}-daily-trend-analysis"
  description         = "Trigger economic trend analysis daily at 8:50 AM Taiwan time"
  schedule_expression = "cron(50 0 * * ? *)" # 00:50 UTC = 08:50 Taiwan (UTC+8)

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target to invoke Lambda function
resource "aws_cloudwatch_event_target" "trend_analyzer" {
  rule      = aws_cloudwatch_event_rule.daily_trend_analysis.name
  target_id = "TrendAnalyzerLambda"
  arn       = aws_lambda_function.trend_analyzer.arn

  # Payload for the Lambda function
  input = jsonencode({
    days = 15 # Analyze last 15 days by default
  })
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_daily" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trend_analyzer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trend_analysis.arn
}
