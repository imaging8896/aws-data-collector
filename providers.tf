terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  # AWS credentials will be sourced from environment variables:
  # AWS_ACCESS_KEY_ID
  # AWS_SECRET_ACCESS_KEY
  # AWS_REGION
  # AWS_SESSION_TOKEN (optional, for temporary credentials)
}
