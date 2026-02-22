# ===== CloudFront Distribution for Static Website =====

# CloudFront Origin Access Control (OAC) for S3
resource "aws_cloudfront_origin_access_control" "trend_charts_oac" {
  name                              = "${var.environment}-${var.project_name}-trend-charts-oac"
  description                       = "OAC for trend charts S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "trend_charts_cdn" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CDN for ${var.environment} ${var.project_name} trend charts"
  default_root_object = "index.html"
  price_class         = "PriceClass_100" # Use only North America and Europe (cheapest)

  origin {
    domain_name              = aws_s3_bucket.trend_charts.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.trend_charts.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.trend_charts_oac.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.trend_charts.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600  # 1 hour
    max_ttl                = 86400 # 24 hours
    compress               = true
  }

  # Cache behavior for HTML files (shorter TTL)
  ordered_cache_behavior {
    path_pattern     = "*.html"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.trend_charts.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 300  # 5 minutes for HTML
    max_ttl                = 3600 # 1 hour
    compress               = true
  }

  # Cache behavior for index.html (even shorter TTL for latest trend)
  ordered_cache_behavior {
    path_pattern     = "index.html"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.trend_charts.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 300 # 5 minutes for index.html (always show latest)
    max_ttl                = 600 # 10 minutes max
    compress               = true
  }

  # Cache behavior for images (longer TTL since we use timestamped filenames)
  ordered_cache_behavior {
    path_pattern     = "charts/*/*.png"
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.trend_charts.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 2592000  # 30 days for timestamped images (immutable)
    max_ttl                = 31536000 # 1 year
    compress               = false    # PNG already compressed
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    # For custom domain, use:
    # acm_certificate_arn      = aws_acm_certificate.cert.arn
    # ssl_support_method       = "sni-only"
    # minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Update S3 bucket policy to allow CloudFront OAC
resource "aws_s3_bucket_policy" "trend_charts_cloudfront" {
  bucket = aws_s3_bucket.trend_charts.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.trend_charts.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.trend_charts_cdn.arn
          }
        }
      }
    ]
  })

  depends_on = [
    aws_s3_bucket_public_access_block.trend_charts_private,
    aws_cloudfront_distribution.trend_charts_cdn
  ]
}

# Update S3 public access block to restrict public access (CloudFront only)
resource "aws_s3_bucket_public_access_block" "trend_charts_private" {
  bucket = aws_s3_bucket.trend_charts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Output CloudFront domain
output "cloudfront_domain_name" {
  value       = aws_cloudfront_distribution.trend_charts_cdn.domain_name
  description = "CloudFront distribution domain name"
}

output "cloudfront_url" {
  value       = "https://${aws_cloudfront_distribution.trend_charts_cdn.domain_name}"
  description = "CloudFront HTTPS URL"
}
