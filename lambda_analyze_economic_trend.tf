# ===== Analyze Economic Trend Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_trend_analyzer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/analyze_economic_trend"
  output_path = "${path.module}/lambda_trend_analyzer_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Create Lambda Layer with dependencies
resource "terraform_data" "install_trend_analyzer_dependencies" {
  triggers_replace = {
    requirements = filemd5("${path.module}/lambda/analyze_economic_trend/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_trend_analyzer || true
      mkdir -p ${path.module}/layer_trend_analyzer/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/lambda/analyze_economic_trend/requirements.txt:/tmp/requirements.txt" \
        -v "$(pwd)/${path.module}/layer_trend_analyzer/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install -r /tmp/requirements.txt -t /var/task --upgrade
      cd ${path.module}/layer_trend_analyzer && zip -r ../lambda_trend_analyzer_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "trend_analyzer_dependencies_layer" {
  filename                 = "${path.module}/lambda_trend_analyzer_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-trend-analyzer-dependencies"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_trend_analyzer_dependencies.id

  depends_on = [terraform_data.install_trend_analyzer_dependencies]
}

# Lambda Function
resource "aws_lambda_function" "trend_analyzer" {
  filename         = data.archive_file.lambda_trend_analyzer_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-trend-analyzer"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_trend_analyzer_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size      = 128  # More memory for data processing
  timeout          = 60   # Allow time for querying and processing
  architectures    = ["arm64"]
  layers           = [aws_lambda_layer_version.trend_analyzer_dependencies_layer.arn]

  environment {
    variables = {
      DYNAMODB_TABLE_NAME       = aws_dynamodb_table.news_urls_table.name
      DYNAMODB_TREND_TABLE_NAME = aws_dynamodb_table.economic_trends_table.name
      ENVIRONMENT               = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_trend_analyzer_logs" {
  name              = "/aws/lambda/${aws_lambda_function.trend_analyzer.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Lambda Destination: Trigger chart generator on success
resource "aws_lambda_function_event_invoke_config" "trend_analyzer_destination" {
  function_name = aws_lambda_function.trend_analyzer.function_name

  destination_config {
    on_success {
      destination = aws_lambda_function.chart_generator.arn
    }
  }
}

# Permission for trend analyzer to invoke chart generator
resource "aws_lambda_permission" "trend_analyzer_invoke_chart" {
  statement_id  = "AllowExecutionFromTrendAnalyzer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chart_generator.function_name
  principal     = "lambda.amazonaws.com"
  source_arn    = aws_lambda_function.trend_analyzer.arn
}

# Lambda URL for easy HTTP access (optional)
resource "aws_lambda_function_url" "trend_analyzer_url" {
  function_name      = aws_lambda_function.trend_analyzer.function_name
  authorization_type = "NONE"  # Change to "AWS_IAM" for production

  cors {
    allow_origins     = ["*"]
    allow_methods     = ["GET", "POST"]
    allow_headers     = ["*"]
    max_age          = 300
  }
}

# Output the function URL
output "trend_analyzer_url" {
  description = "URL for the economic trend analyzer"
  value       = aws_lambda_function_url.trend_analyzer_url.function_url
}
