# DynamoDB Table for News URLs
resource "aws_dynamodb_table" "news_urls_table" {
  name         = "${var.environment}-${var.project_name}-news-urls"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "url"

  attribute {
    name = "url"
    type = "S"
  }

  # Global Secondary Index for querying by timestamp
  global_secondary_index {
    name            = "TimestampIndex"
    hash_key        = "timestamp"
    projection_type = "ALL"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  # Point-in-time recovery for data protection (minimal cost)
  point_in_time_recovery {
    enabled = true
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${var.environment}-${var.project_name}-lambda-role"

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

# IAM Policy for Lambda to access DynamoDB
resource "aws_iam_role_policy" "lambda_dynamodb_policy" {
  name = "${var.environment}-${var.project_name}-lambda-dynamodb-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.news_urls_table.arn,
          "${aws_dynamodb_table.news_urls_table.arn}/index/*"
        ]
      }
    ]
  })
}

# Attach basic execution role for CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

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
      mkdir -p ${path.module}/layer/python
      docker run --rm --entrypoint "" \
        -v "$(pwd)/${path.module}/lambda/get_news_urls/requirements.txt:/tmp/requirements.txt" \
        -v "$(pwd)/${path.module}/layer/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        pip install -r /tmp/requirements.txt -t /var/task --upgrade
    EOT
  }
}

data "archive_file" "lambda_layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/layer"
  output_path = "${path.module}/lambda_layer.zip"

  depends_on = [terraform_data.install_dependencies]
}

resource "aws_lambda_layer_version" "dependencies_layer" {
  filename            = data.archive_file.lambda_layer_zip.output_path
  layer_name          = "${var.environment}-${var.project_name}-dependencies"
  compatible_runtimes = [var.lambda_runtime]
  source_code_hash    = data.archive_file.lambda_layer_zip.output_base64sha256

  depends_on = [data.archive_file.lambda_layer_zip]
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
  layers = [aws_lambda_layer_version.dependencies_layer.arn]

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
