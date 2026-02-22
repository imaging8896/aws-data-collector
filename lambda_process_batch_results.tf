# ===== Process Batch Results Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_batch_processor_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/process_batch_results"
  output_path = "${path.module}/lambda_batch_processor_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Create Lambda Layer with dependencies
resource "terraform_data" "install_batch_processor_dependencies" {
  triggers_replace = {
    requirements = filemd5("${path.module}/lambda/process_batch_results/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_batch_processor || true
      mkdir -p ${path.module}/layer_batch_processor/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/lambda/process_batch_results/requirements.txt:/tmp/requirements.txt" \
        -v "$(pwd)/${path.module}/layer_batch_processor/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install -r /tmp/requirements.txt -t /var/task --upgrade
      cd ${path.module}/layer_batch_processor && zip -r ../lambda_batch_processor_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "batch_processor_dependencies_layer" {
  filename                 = "${path.module}/lambda_batch_processor_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-batch-processor-dependencies"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_batch_processor_dependencies.id

  depends_on = [terraform_data.install_batch_processor_dependencies]
}

# Lambda Function
resource "aws_lambda_function" "batch_processor" {
  filename         = data.archive_file.lambda_batch_processor_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-batch-processor"
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.handler"
  source_code_hash = data.archive_file.lambda_batch_processor_zip.output_base64sha256
  runtime          = var.lambda_runtime
  memory_size      = 128
  timeout          = var.lambda_timeout
  architectures    = ["arm64"]
  layers           = [aws_lambda_layer_version.batch_processor_dependencies_layer.arn]

  environment {
    variables = {
      DYNAMODB_NEWS_TABLE_NAME   = aws_dynamodb_table.news_urls_table.name
      DYNAMODB_BATCH_TABLE_NAME  = aws_dynamodb_table.batch_requests_table.name
      ENVIRONMENT                = var.environment
      GEMINI_API_KEY_SECRET_NAME = aws_secretsmanager_secret.gemini_api_key.name
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_batch_processor_logs" {
  name              = "/aws/lambda/${aws_lambda_function.batch_processor.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge rule to trigger batch processor every 5 minutes
resource "aws_cloudwatch_event_rule" "batch_processor_schedule" {
  name                = "${var.environment}-${var.project_name}-batch-processor-schedule"
  description         = "Trigger batch processor every 15 minutes"
  schedule_expression = "rate(15 minutes)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "batch_processor_target" {
  rule      = aws_cloudwatch_event_rule.batch_processor_schedule.name
  target_id = "BatchProcessorLambda"
  arn       = aws_lambda_function.batch_processor.arn
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_batch_processor" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.batch_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.batch_processor_schedule.arn
}
