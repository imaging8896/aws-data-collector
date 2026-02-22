# ===== Get News Content Lambda =====

# Lambda function source code archive for get_news_content
data "archive_file" "lambda_content_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/get_news_content"
  output_path = "${path.module}/lambda_content_function.zip"
  excludes    = ["requirements.txt", "__pycache__"]
}

# Create Lambda Layer with dependencies for get_news_content
resource "terraform_data" "install_content_dependencies" {
  triggers_replace = {
    requirements = filemd5("${path.module}/lambda/get_news_content/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_content || true
      mkdir -p ${path.module}/layer_content/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/lambda/get_news_content/requirements.txt:/tmp/requirements.txt" \
        -v "$(pwd)/${path.module}/layer_content/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install -r /tmp/requirements.txt -t /var/task --upgrade
      cd ${path.module}/layer_content && zip -r ../lambda_content_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "content_dependencies_layer" {
  filename                 = "${path.module}/lambda_content_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-content-dependencies"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_content_dependencies.id

  depends_on = [terraform_data.install_content_dependencies]
}

# Lambda Function for get_news_content
resource "aws_lambda_function" "content_collector" {
  filename         = data.archive_file.lambda_content_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-content-collector"
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.handler"
  source_code_hash = data.archive_file.lambda_content_zip.output_base64sha256
  runtime          = var.lambda_runtime
  memory_size      = 192
  timeout          = 60
  architectures    = ["arm64"]
  layers           = [aws_lambda_layer_version.content_dependencies_layer.arn]

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.news_urls_table.name
      ENVIRONMENT         = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group for content collector
resource "aws_cloudwatch_log_group" "lambda_content_logs" {
  name              = "/aws/lambda/${aws_lambda_function.content_collector.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
