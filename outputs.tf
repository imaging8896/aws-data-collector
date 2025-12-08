output "lambda_function_name" {
  description = "Name of the Lambda function for getting news URLs"
  value       = aws_lambda_function.data_collector.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function for getting news URLs"
  value       = aws_lambda_function.data_collector.arn
}

output "lambda_content_function_name" {
  description = "Name of the Lambda function for getting news content"
  value       = aws_lambda_function.content_collector.function_name
}

output "lambda_content_function_arn" {
  description = "ARN of the Lambda function for getting news content"
  value       = aws_lambda_function.content_collector.arn
}

output "lambda_dispatcher_function_name" {
  description = "Name of the dispatcher Lambda function"
  value       = aws_lambda_function.dispatcher.function_name
}

output "lambda_dispatcher_function_arn" {
  description = "ARN of the dispatcher Lambda function"
  value       = aws_lambda_function.dispatcher.arn
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB news URLs table"
  value       = aws_dynamodb_table.news_urls_table.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB news URLs table"
  value       = aws_dynamodb_table.news_urls_table.arn
}
