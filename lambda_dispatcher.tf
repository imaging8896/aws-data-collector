# ===== Dispatcher Lambda =====

# Lambda function source code archive for dispatcher
data "archive_file" "lambda_dispatcher_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/dispatcher"
  output_path = "${path.module}/lambda_dispatcher_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Lambda Function for dispatcher
resource "aws_lambda_function" "dispatcher" {
  filename         = data.archive_file.lambda_dispatcher_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-dispatcher"
  role            = aws_iam_role.dispatcher_lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_dispatcher_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 128
  timeout         = 60

  environment {
    variables = {
      GET_NEWS_URLS_FUNCTION_NAME = aws_lambda_function.data_collector.function_name
      ENVIRONMENT                 = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# IAM Role for Dispatcher Lambda
resource "aws_iam_role" "dispatcher_lambda_role" {
  name = "${var.environment}-${var.project_name}-dispatcher-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# IAM Policy for Dispatcher Lambda to invoke other Lambdas
resource "aws_iam_role_policy" "dispatcher_lambda_invoke_policy" {
  name = "${var.environment}-${var.project_name}-dispatcher-invoke-policy"
  role = aws_iam_role.dispatcher_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.data_collector.arn
        ]
      }
    ]
  })
}

# Attach basic execution role for CloudWatch Logs
resource "aws_iam_role_policy_attachment" "dispatcher_lambda_basic_execution" {
  role       = aws_iam_role.dispatcher_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# CloudWatch Log Group for dispatcher
resource "aws_cloudwatch_log_group" "lambda_dispatcher_logs" {
  name              = "/aws/lambda/${aws_lambda_function.dispatcher.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge Rule to trigger Dispatcher Lambda hourly
resource "aws_cloudwatch_event_rule" "hourly_dispatcher_trigger" {
  name                = "${var.environment}-${var.project_name}-hourly-dispatcher"
  description         = "Trigger dispatcher Lambda hourly to collect news URLs"
  schedule_expression = "rate(1 hour)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge Target for dispatcher
resource "aws_cloudwatch_event_target" "lambda_dispatcher_target" {
  rule      = aws_cloudwatch_event_rule.hourly_dispatcher_trigger.name
  target_id = "LambdaDispatcherTarget"
  arn       = aws_lambda_function.dispatcher.arn
}

# Lambda permission for EventBridge to invoke dispatcher
resource "aws_lambda_permission" "allow_eventbridge_dispatcher" {
  statement_id  = "AllowExecutionFromEventBridgeDispatcher"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_dispatcher_trigger.arn
}
