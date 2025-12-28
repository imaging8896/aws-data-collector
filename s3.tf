# ===== S3 Bucket for Trend Charts =====

# S3 Bucket for storing generated chart images
resource "aws_s3_bucket" "trend_charts" {
  bucket = "${var.environment}-${var.project_name}-trend-charts"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Purpose     = "Store trend analysis chart images"
  }
}

# Enable versioning for chart history
resource "aws_s3_bucket_versioning" "trend_charts" {
  bucket = aws_s3_bucket.trend_charts.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption for security
resource "aws_s3_bucket_server_side_encryption_configuration" "trend_charts" {
  bucket = aws_s3_bucket.trend_charts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Lifecycle policy to optimize costs
resource "aws_s3_bucket_lifecycle_configuration" "trend_charts" {
  bucket = aws_s3_bucket.trend_charts.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {}

    # Move to Infrequent Access after 30 days
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    # Move to Glacier after 90 days
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }

    # Delete after 365 days (optional, remove if you want to keep forever)
    expiration {
      days = 365
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Block public access (charts accessed via signed URLs or CloudFront)
resource "aws_s3_bucket_public_access_block" "trend_charts" {
  bucket = aws_s3_bucket.trend_charts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CORS configuration (if accessed from web browser)
resource "aws_s3_bucket_cors_configuration" "trend_charts" {
  bucket = aws_s3_bucket.trend_charts.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]  # Restrict this to your domain in production
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Output the bucket name for Lambda environment variable
output "trend_charts_bucket_name" {
  value       = aws_s3_bucket.trend_charts.id
  description = "S3 bucket name for trend charts"
}

output "trend_charts_bucket_arn" {
  value       = aws_s3_bucket.trend_charts.arn
  description = "S3 bucket ARN for trend charts"
}
