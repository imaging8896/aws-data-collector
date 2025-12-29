# ===== EventBridge Direct Triggers for News Collection =====

# EventBridge Rule to trigger finance news collection hourly
resource "aws_cloudwatch_event_rule" "hourly_finance_news_trigger" {
  name                = "${var.environment}-${var.project_name}-hourly-finance-news"
  description         = "Trigger news URL collection for finance category hourly"
  schedule_expression = "rate(1 hour)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge Target for finance news
resource "aws_cloudwatch_event_target" "finance_news_target" {
  rule      = aws_cloudwatch_event_rule.hourly_finance_news_trigger.name
  target_id = "FinanceNewsCollector"
  arn       = aws_lambda_function.data_collector.arn
  
  input = jsonencode({
    category_id = "CAAqJQgKIh9DQkFTRVFvSUwyMHZNREpmTjNRU0JYcG9MVlJYS0FBUAE"
  })
}

# Lambda permission for EventBridge to invoke for finance news
resource "aws_lambda_permission" "allow_eventbridge_finance" {
  statement_id  = "AllowExecutionFromEventBridgeFinance"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_finance_news_trigger.arn
}

# EventBridge Rule to trigger business news collection hourly
resource "aws_cloudwatch_event_rule" "hourly_business_news_trigger" {
  name                = "${var.environment}-${var.project_name}-hourly-business-news"
  description         = "Trigger news URL collection for business category hourly"
  schedule_expression = "rate(1 hour)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge Target for business news
resource "aws_cloudwatch_event_target" "business_news_target" {
  rule      = aws_cloudwatch_event_rule.hourly_business_news_trigger.name
  target_id = "BusinessNewsCollector"
  arn       = aws_lambda_function.data_collector.arn
  
  input = jsonencode({
    category_id = "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JYcG9MVlJYR2dKVVZ5Z0FQAQ"
  })
}

# Lambda permission for EventBridge to invoke for business news
resource "aws_lambda_permission" "allow_eventbridge_business" {
  statement_id  = "AllowExecutionFromEventBridgeBusiness"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_business_news_trigger.arn
}
