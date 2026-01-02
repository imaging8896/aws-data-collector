# ===== Generate Static Website Lambda =====

# Lambda function source code archive
data "archive_file" "lambda_static_website_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/generate_static_website"
  output_path = "${path.module}/lambda_static_website_function.zip"
  excludes    = ["__pycache__"]
}

# Lambda Function
resource "aws_lambda_function" "static_website_generator" {
  filename         = data.archive_file.lambda_static_website_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-static-website-generator"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_static_website_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 128
  timeout         = 30
  architectures   = ["arm64"]

  environment {
    variables = {
      DYNAMODB_STATS_TABLE_NAME = aws_dynamodb_table.daily_stats_table.name
      S3_CHART_BUCKET_NAME      = aws_s3_bucket.trend_charts.id
      CLOUDFRONT_DOMAIN         = aws_cloudfront_distribution.trend_charts_cdn.domain_name
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
resource "aws_cloudwatch_log_group" "lambda_static_website_logs" {
  name              = "/aws/lambda/${aws_lambda_function.static_website_generator.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
