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
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.news_urls_table.arn,
          "${aws_dynamodb_table.news_urls_table.arn}/index/*",
          aws_dynamodb_table.batch_requests_table.arn,
          "${aws_dynamodb_table.batch_requests_table.arn}/index/*",
          aws_dynamodb_table.daily_stats_table.arn,
          "${aws_dynamodb_table.daily_stats_table.arn}/index/*",
          aws_dynamodb_table.market_data_table.arn,
          "${aws_dynamodb_table.market_data_table.arn}/index/*",
          aws_dynamodb_table.investor_data_table.arn,
          "${aws_dynamodb_table.investor_data_table.arn}/index/*"
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

# IAM Policy for Lambda to invoke other Lambda functions
resource "aws_iam_role_policy" "lambda_invoke_policy" {
  name = "${var.environment}-${var.project_name}-lambda-invoke-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          "arn:aws:lambda:*:*:function:${var.environment}-${var.project_name}-*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda to read Secrets Manager
resource "aws_iam_role_policy" "lambda_secrets_policy" {
  name = "${var.environment}-${var.project_name}-lambda-secrets-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:aws:secretsmanager:*:*:secret:${var.environment}/${var.project_name}/*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda to access S3 (for chart storage)
resource "aws_iam_role_policy" "lambda_s3_policy" {
  name = "${var.environment}-${var.project_name}-lambda-s3-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "${aws_s3_bucket.trend_charts.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.trend_charts.arn
        ]
      }
    ]
  })
}
