# Terraform test for Lambda Notify Discord
# Tests the lambda_notify_discord.tf module configuration

# Mock provider to avoid actual AWS API calls during testing
mock_provider "aws" {}

# Variable definitions for testing
variables {
  environment           = "test"
  project_name          = "aws-data-collector"
  lambda_runtime        = "python3.13"
  lambda_timeout        = 30
  dynamodb_billing_mode = "PAY_PER_REQUEST"
  gemini_api_key        = "test-api-key-12345"
  discord_webhook_url   = "https://discord.com/api/webhooks/test/test"
  categories            = "test-categories"
}

# Test: Verify Lambda function resource configuration
run "verify_lambda_function_configuration" {
  command = plan

  # Assert Lambda function has correct naming convention
  assert {
    condition     = aws_lambda_function.notify_discord.function_name == "test-aws-data-collector-notify-discord"
    error_message = "Lambda function name should follow the naming convention: {environment}-{project_name}-notify-discord"
  }

  # Assert Lambda function uses correct handler
  assert {
    condition     = aws_lambda_function.notify_discord.handler == "main.handler"
    error_message = "Lambda function handler should be 'main.handler'"
  }

  # Assert Lambda function uses correct runtime
  assert {
    condition     = aws_lambda_function.notify_discord.runtime == "python3.13"
    error_message = "Lambda function runtime should be 'python3.13'"
  }

  # Assert Lambda function uses ARM64 architecture
  assert {
    condition     = contains(aws_lambda_function.notify_discord.architectures, "arm64")
    error_message = "Lambda function should use 'arm64' architecture for cost optimization"
  }

  # Assert Lambda function has appropriate memory size
  assert {
    condition     = aws_lambda_function.notify_discord.memory_size == 128
    error_message = "Lambda function memory size should be 128 MB"
  }

  # Assert Lambda function has appropriate timeout
  assert {
    condition     = aws_lambda_function.notify_discord.timeout == 30
    error_message = "Lambda function timeout should be 30 seconds"
  }
}

# Test: Verify Lambda function environment variables
run "verify_lambda_environment_variables" {
  command = plan

  # Assert environment variable for Discord webhook parameter name is set
  assert {
    condition     = aws_lambda_function.notify_discord.environment[0].variables["ENVIRONMENT"] == "test"
    error_message = "Lambda function should have ENVIRONMENT variable set to 'test'"
  }
}

# Test: Verify Lambda function has required tags
run "verify_lambda_function_tags" {
  command = plan

  # Assert Lambda function has Project tag
  assert {
    condition     = aws_lambda_function.notify_discord.tags["Project"] == "aws-data-collector"
    error_message = "Lambda function should have 'Project' tag set to project_name"
  }

  # Assert Lambda function has Environment tag
  assert {
    condition     = aws_lambda_function.notify_discord.tags["Environment"] == "test"
    error_message = "Lambda function should have 'Environment' tag set to environment"
  }

  # Assert Lambda function has ManagedBy tag
  assert {
    condition     = aws_lambda_function.notify_discord.tags["ManagedBy"] == "Terraform"
    error_message = "Lambda function should have 'ManagedBy' tag set to 'Terraform'"
  }
}

# Test: Verify CloudWatch Log Group configuration
run "verify_cloudwatch_log_group" {
  command = plan

  # Assert log group has correct name pattern
  assert {
    condition     = aws_cloudwatch_log_group.lambda_notify_discord_logs.retention_in_days == 7
    error_message = "CloudWatch Log Group retention should be 7 days"
  }

  # Assert log group has Project tag
  assert {
    condition     = aws_cloudwatch_log_group.lambda_notify_discord_logs.tags["Project"] == "aws-data-collector"
    error_message = "CloudWatch Log Group should have 'Project' tag"
  }

  # Assert log group has Environment tag
  assert {
    condition     = aws_cloudwatch_log_group.lambda_notify_discord_logs.tags["Environment"] == "test"
    error_message = "CloudWatch Log Group should have 'Environment' tag"
  }
}

# Test: Verify SSM Parameter configuration
run "verify_ssm_parameter" {
  command = plan

  # Assert SSM parameter uses SecureString type
  assert {
    condition     = aws_ssm_parameter.discord_webhook_url.type == "SecureString"
    error_message = "SSM parameter for Discord webhook URL should use SecureString type for security"
  }

  # Assert SSM parameter has correct name pattern
  assert {
    condition     = aws_ssm_parameter.discord_webhook_url.name == "/test/aws-data-collector/discord-webhook-url"
    error_message = "SSM parameter name should follow the pattern: /{environment}/{project_name}/discord-webhook-url"
  }
}
