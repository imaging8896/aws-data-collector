# ===== SQS Queue for News Content Processing =====

# SQS Queue for news content collection tasks
resource "aws_sqs_queue" "news_content_queue" {
  name                       = "${var.environment}-${var.project_name}-news-content-queue"
  delay_seconds              = 0
  max_message_size           = 262144 # 256 KB
  message_retention_seconds  = 345600 # 4 days
  receive_wait_time_seconds  = 0
  visibility_timeout_seconds = var.lambda_timeout * 6 # 6x Lambda timeout for retries

  # Dead Letter Queue for failed messages
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.news_content_dlq.arn
    maxReceiveCount     = 3 # Retry up to 3 times
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Dead Letter Queue for failed messages
resource "aws_sqs_queue" "news_content_dlq" {
  name                      = "${var.environment}-${var.project_name}-news-content-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Lambda Event Source Mapping - SQS to Lambda
resource "aws_lambda_event_source_mapping" "sqs_to_content_collector" {
  event_source_arn = aws_sqs_queue.news_content_queue.arn
  function_name    = aws_lambda_function.content_collector.arn
  batch_size       = 1 # Process one URL at a time
  enabled          = true

  # Process messages with best effort
  function_response_types = ["ReportBatchItemFailures"]
}

# IAM Policy for Lambda to receive messages from SQS
resource "aws_iam_policy" "lambda_sqs_policy" {
  name        = "${var.environment}-${var.project_name}-lambda-sqs-policy"
  description = "Allow Lambda to receive messages from SQS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.news_content_queue.arn
      }
    ]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Attach SQS policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_sqs_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_sqs_policy.arn
}

# IAM Policy for Lambda to send messages to SQS
resource "aws_iam_policy" "lambda_sqs_send_policy" {
  name        = "${var.environment}-${var.project_name}-lambda-sqs-send-policy"
  description = "Allow Lambda to send messages to SQS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueUrl"
        ]
        Resource = aws_sqs_queue.news_content_queue.arn
      }
    ]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Attach SQS send policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_sqs_send_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_sqs_send_policy.arn
}

# Output SQS Queue URL
output "news_content_queue_url" {
  value       = aws_sqs_queue.news_content_queue.url
  description = "URL of the news content processing queue"
}

output "news_content_queue_arn" {
  value       = aws_sqs_queue.news_content_queue.arn
  description = "ARN of the news content processing queue"
}
