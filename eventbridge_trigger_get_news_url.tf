# ===== EventBridge Direct Triggers for News Collection =====

# EventBridge Rule to trigger news collection hourly (both finance and business)
resource "aws_cloudwatch_event_rule" "hourly_news_trigger" {
  name                = "${var.environment}-${var.project_name}-hourly-news"
  description         = "Trigger news URL collection hourly"
  schedule_expression = "rate(1 hour)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge Target for finance news
resource "aws_cloudwatch_event_target" "finance_news_target" {
  rule      = aws_cloudwatch_event_rule.hourly_news_trigger.name
  target_id = "FinanceNewsCollector"
  arn       = aws_lambda_function.data_collector.arn
  
  input = jsonencode({
    category_id = "CAAqJQgKIh9DQkFTRVFvSUwyMHZNREpmTjNRU0JYcG9MVlJYS0FBUAE"
  })
}

# EventBridge Target for business news (same rule, different target)
resource "aws_cloudwatch_event_target" "business_news_target" {
  rule      = aws_cloudwatch_event_rule.hourly_news_trigger.name
  target_id = "BusinessNewsCollector"
  arn       = aws_lambda_function.data_collector.arn
  
  input = jsonencode({
    category_id = "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JYcG9MVlJYR2dKVVZ5Z0FQAQ"
  })
}

# Lambda permission for EventBridge to invoke
resource "aws_lambda_permission" "allow_eventbridge_news" {
  statement_id  = "AllowExecutionFromEventBridgeNews"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_news_trigger.arn
}
