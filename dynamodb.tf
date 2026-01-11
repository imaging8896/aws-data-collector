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

# DynamoDB Table for Gemini Batch Requests
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
