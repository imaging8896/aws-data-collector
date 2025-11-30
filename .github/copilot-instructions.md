# AWS Data Collector - AI Agent Instructions

## Project Purpose
Minimize or eliminate costs for data collection infrastructure on AWS using cost-optimized serverless and managed services.

## Technology Stack
- **Infrastructure**: Terraform for IaC (Infrastructure as Code)
- **Cloud Provider**: AWS
- **Focus**: Cost-effective data collection and processing

## Development Workflow

### Terraform Commands
```bash
terraform init          # Initialize provider and modules
terraform plan          # Preview infrastructure changes
terraform apply         # Apply infrastructure changes
terraform destroy       # Tear down infrastructure
```

### Sensitive Data
- **Never commit** `.tfvars` or `.tfvars.json` files - these contain environment-specific and sensitive data
- Use `.tfvars` files for environment-specific variables (dev, staging, prod)
- Secrets should be referenced from AWS Secrets Manager or Parameter Store, not hardcoded

## Architecture Principles

### Cost Optimization
This project prioritizes **minimal cost** over other factors. When suggesting solutions:
- Prefer serverless (Lambda, EventBridge, S3) over always-on infrastructure
- Use pay-per-request pricing models when possible
- Consider AWS Free Tier eligible services first
- Recommend spot instances or Fargate Spot for batch processing
- Use S3 lifecycle policies and Intelligent-Tiering for storage

### Expected AWS Services
Based on the cost-optimization goal, likely services include:
- **Compute**: Lambda functions for event-driven processing
- **Storage**: S3 for data lake/storage
- **Orchestration**: EventBridge, Step Functions, or SQS
- **Database**: DynamoDB (on-demand) or Aurora Serverless for metadata
- **Monitoring**: CloudWatch Logs with retention policies

## Terraform Patterns

### File Organization
When creating Terraform code, follow this structure:
```
main.tf           # Primary resources
variables.tf      # Input variables
outputs.tf        # Output values
providers.tf      # Provider configuration
terraform.tfvars.example  # Example variables file (safe to commit)
```

### Resource Naming
Use consistent naming with environment and purpose:
```hcl
resource "aws_lambda_function" "data_collector" {
  function_name = "${var.environment}-${var.project_name}-collector"
  # ...
}
```

## Getting Started
Since this is a new project, when adding infrastructure:
1. Start with `providers.tf` defining AWS provider and required versions
2. Define reusable variables in `variables.tf`
3. Create modular, single-purpose resources
4. Tag all resources with `Project`, `Environment`, and `ManagedBy = "Terraform"`
5. Create example `.tfvars.example` file with dummy values

## Questions to Consider
When developing this codebase, always ask:
- Can this run on-demand instead of continuously?
- Is there a more cost-effective AWS service for this use case?
- Can we batch operations to reduce invocations?
- Have we set appropriate CloudWatch log retention periods?
