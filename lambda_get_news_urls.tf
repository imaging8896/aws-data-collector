# ===== Get News URLs Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/get_news_urls"
  output_path = "${path.module}/lambda_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Create Lambda Layer with dependencies using Docker for Lambda-compatible build
resource "terraform_data" "install_dependencies" {
  triggers_replace = {
    requirements = filemd5("${path.module}/lambda/get_news_urls/requirements.txt")
  }

  provisioner "local-exec" {
    # If encounter docker pull denied do following commands to login to public ECR and retry
    # docker logout public.ecr.aws
    # aws ecr-public get-login-password | docker login --username AWS --password-stdin public.ecr.aws
    command = <<EOT
      rm -rf ${path.module}/layer || true
      mkdir -p ${path.module}/layer/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/lambda/get_news_urls/requirements.txt:/tmp/requirements.txt" \
        -v "$(pwd)/${path.module}/layer/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install -r /tmp/requirements.txt -t /var/task --upgrade
      cd ${path.module}/layer && zip -r ../lambda_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "dependencies_layer" {
  filename               = "${path.module}/lambda_layer.zip"
  layer_name             = "${var.environment}-${var.project_name}-dependencies"
  compatible_runtimes    = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash       = terraform_data.install_dependencies.id

  depends_on = [terraform_data.install_dependencies]
}

# Lambda Function
resource "aws_lambda_function" "data_collector" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-collector"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = var.lambda_memory_size
  timeout         = var.lambda_timeout
  architectures    = ["arm64"]
  layers           = [aws_lambda_layer_version.dependencies_layer.arn]

  environment {
    variables = {
      DYNAMODB_TABLE_NAME       = aws_dynamodb_table.news_urls_table.name
      ENVIRONMENT               = var.environment
      CONTENT_COLLECTOR_LAMBDA  = aws_lambda_function.content_collector.function_name
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group with retention policy for cost optimization
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.data_collector.function_name}"
  retention_in_days = 7 # Short retention for cost optimization

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
