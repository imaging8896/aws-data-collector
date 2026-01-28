# ===== Check Trading Signals Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_check_trading_signals_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/check_trading_signals"
  output_path = "${path.module}/lambda_check_trading_signals_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Create Lambda Layer with google-genai dependency
resource "terraform_data" "install_check_signals_dependencies" {
  triggers_replace = {
    version = "1"
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_check_signals || true
      mkdir -p ${path.module}/layer_check_signals/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/layer_check_signals/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install google-genai -t /var/task --upgrade
      cd ${path.module}/layer_check_signals && zip -r ../lambda_check_signals_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "check_signals_dependencies_layer" {
  filename                 = "${path.module}/lambda_check_signals_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-check-signals-dependencies"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_check_signals_dependencies.id

  depends_on = [terraform_data.install_check_signals_dependencies]
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
  layers           = [aws_lambda_layer_version.check_signals_dependencies_layer.arn]

  environment {
    variables = {
      DYNAMODB_STATS_TABLE_NAME    = aws_dynamodb_table.daily_stats_table.name
      GEMINI_API_KEY_SECRET_NAME   = aws_secretsmanager_secret.gemini_api_key.name
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
