# DynamoDB Table for News URLs
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
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

# DynamoDB Table for Index Representative Stocks
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
resource "aws_dynamodb_table" "index_stocks_table" {
  name         = "${var.environment}-${var.project_name}-index-stocks"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "index_name"

  attribute {
    name = "index_name"
    type = "S"
  }

  # Point-in-time recovery for data protection
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

# DynamoDB Table for Gemini Batch Requests
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
resource "aws_dynamodb_table" "batch_requests_table" {
  name         = "${var.environment}-${var.project_name}-batch-requests"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "batch_id"

  attribute {
    name = "batch_id"
    type = "S"
  }

  # GSI for querying by status
  global_secondary_index {
    name            = "URL"
    hash_key        = "url"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  attribute {
    name = "url"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "N"
  }

  # Point-in-time recovery for data protection
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

# DynamoDB Table for Daily Statistics (Aggregated Data)
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
resource "aws_dynamodb_table" "daily_stats_table" {
  name         = "${var.environment}-${var.project_name}-daily-stats"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "date"

  attribute {
    name = "date"
    type = "S"
  }

  # GSI for querying by update time
  global_secondary_index {
    name            = "UpdatedAtIndex"
    hash_key        = "updated_at"
    projection_type = "ALL"
  }

  attribute {
    name = "updated_at"
    type = "N"
  }

  # Point-in-time recovery for data protection
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

# DynamoDB Table for Market Data (Taiwan Stock Index and Stocks)
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
resource "aws_dynamodb_table" "market_data_table" {
  name         = "${var.environment}-${var.project_name}-market-data"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "symbol"
  range_key    = "date"

  attribute {
    name = "symbol"
    type = "S"
  }

  attribute {
    name = "date"
    type = "S"
  }

  # GSI for querying by date across all symbols
  global_secondary_index {
    name            = "DateIndex"
    hash_key        = "date"
    range_key       = "symbol"
    projection_type = "ALL"
  }

  # Point-in-time recovery for data protection
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

# DynamoDB Table for Institutional Investor Data
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
resource "aws_dynamodb_table" "investor_data_table" {
  name         = "${var.environment}-${var.project_name}-investor-data"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "date"

  attribute {
    name = "date"
    type = "S"
  }

  # Point-in-time recovery for data protection
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

# DynamoDB Table for Daily Index Data (TWSE Indices)
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
resource "aws_dynamodb_table" "index_data_table" {
  name         = "${var.environment}-${var.project_name}-index-data"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "name"
  range_key    = "date"

  attribute {
    name = "name"
    type = "S"
  }

  attribute {
    name = "date"
    type = "S"
  }

  # GSI for querying by date across all indices
  global_secondary_index {
    name            = "DateIndex"
    hash_key        = "date"
    range_key       = "name"
    projection_type = "ALL"
  }

  # Point-in-time recovery for data protection
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

# DynamoDB Table for Market Statistics (上漲/下跌/平盤家數)
#checkov:skip=CKV_AWS_119:Using AWS managed encryption instead of CMK for cost optimization
resource "aws_dynamodb_table" "market_stats_table" {
  name         = "${var.environment}-${var.project_name}-market-stats"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "date"

  attribute {
    name = "date"
    type = "S"
  }

  # Point-in-time recovery for data protection
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
