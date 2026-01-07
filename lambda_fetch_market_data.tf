# ===== Fetch Market Data Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_fetch_market_data_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/fetch_market_data"
  output_path = "${path.module}/lambda_fetch_market_data_function.zip"
  excludes    = ["__pycache__"]
}

# Create Lambda Layer with curl_cffi dependency
resource "terraform_data" "install_fetch_market_data_dependencies" {
  triggers_replace = {
    version = "1"
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_fetch_market_data || true
      mkdir -p ${path.module}/layer_fetch_market_data/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/layer_fetch_market_data/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install curl_cffi -t /var/task --upgrade
      cd ${path.module}/layer_fetch_market_data && zip -r ../lambda_fetch_market_data_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "fetch_market_data_dependencies_layer" {
  filename                 = "${path.module}/lambda_fetch_market_data_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-fetch-market-data-dependencies"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_fetch_market_data_dependencies.id

  depends_on = [terraform_data.install_fetch_market_data_dependencies]
}

# Lambda Function
resource "aws_lambda_function" "fetch_market_data" {
  filename         = data.archive_file.lambda_fetch_market_data_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-fetch-market-data"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_fetch_market_data_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 128
  timeout         = 60
  architectures   = ["arm64"]
  layers          = [aws_lambda_layer_version.fetch_market_data_dependencies_layer.arn]

  environment {
    variables = {
      MARKET_DATA_TABLE_NAME = aws_dynamodb_table.market_data_table.name
      INVESTOR_DATA_TABLE_NAME = aws_dynamodb_table.investor_data_table.name
      ENVIRONMENT         = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_fetch_market_data_logs" {
  name              = "/aws/lambda/${aws_lambda_function.fetch_market_data.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger daily at 16:00 Taiwan time (08:00 UTC)
resource "aws_cloudwatch_event_rule" "fetch_market_data_schedule" {
  name                = "${var.environment}-${var.project_name}-fetch-market-data-schedule"
  description         = "Trigger market data fetch daily at 16:00 Taiwan time"
  schedule_expression = "cron(0 8 * * ? *)"  # 08:00 UTC = 16:00 Taiwan (UTC+8)

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "fetch_market_data_target" {
  rule      = aws_cloudwatch_event_rule.fetch_market_data_schedule.name
  target_id = "FetchMarketDataLambda"
  arn       = aws_lambda_function.fetch_market_data.arn

  input = jsonencode({
    data_type = "index",
    index_names = ["tw_index", "2330"],
    from_days   = 7,
  })
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_fetch_market_data" {
  statement_id  = "AllowExecutionFromEventBridgeIndexData"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fetch_market_data.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.fetch_market_data_schedule.arn
}


# EventBridge rule to trigger daily at 19:00 Taiwan time (11:00 UTC)
resource "aws_cloudwatch_event_rule" "fetch_investor_data_schedule" {
  name                = "${var.environment}-${var.project_name}-fetch-investor-data-schedule"
  description         = "Trigger investor data fetch daily at 19:00 Taiwan time"
  schedule_expression = "cron(0 11 * * ? *)"  # 11:00 UTC = 19:00 Taiwan (UTC+8)

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "fetch_investor_data_target" {
  rule      = aws_cloudwatch_event_rule.fetch_investor_data_schedule.name
  target_id = "FetchInvestorDataLambda"
  arn       = aws_lambda_function.fetch_market_data.arn

  input = jsonencode({
    data_type = "investor"
  })
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_fetch_investor_data" {
  statement_id  = "AllowExecutionFromEventBridgeInvestorData"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fetch_market_data.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.fetch_investor_data_schedule.arn
}
