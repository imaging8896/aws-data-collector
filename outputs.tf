output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.data_collector.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.data_collector.arn
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB news URLs table"
  value       = aws_dynamodb_table.news_urls_table.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB news URLs table"
  value       = aws_dynamodb_table.news_urls_table.arn
}
