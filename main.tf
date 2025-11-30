# DynamoDB Table
resource "aws_dynamodb_table" "data_table" {
  name         = "${var.environment}-${var.project_name}-data"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "id"
  range_key    = "timestamp"

  attribute {
    name = "id"
    type = "S"
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
        Resource = aws_dynamodb_table.data_table.arn
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
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda_function.zip"
}

# Lambda Function
resource "aws_lambda_function" "data_collector" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-collector"
  role            = aws_iam_role.lambda_role.arn
  handler         = "index.handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = var.lambda_memory_size
  timeout         = var.lambda_timeout

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.data_table.name
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
