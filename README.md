# aws-data-collector

Minimize or free cost of data collector infrastructure using AWS serverless services.

## Architecture

This project uses cost-optimized AWS services:
- **Lambda**: Event-driven compute (pay per invocation)
- **DynamoDB**: NoSQL database with on-demand billing (pay per request)
- **CloudWatch Logs**: 7-day retention for cost optimization

## Prerequisites

- [Terraform](https://www.terraform.io/downloads.html) >= 1.0
- AWS Account with appropriate permissions
- AWS credentials configured via environment variables

## Setup

### 1. Configure AWS Credentials

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` with your AWS credentials:
```bash
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
```

Load environment variables:
```bash
# On macOS/Linux
export $(cat .env | xargs)

# Or use direnv (recommended)
direnv allow
```

### 2. Configure Terraform Variables

Create `terraform.tfvars` from the example:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your desired configuration.

### 3. Deploy Infrastructure

```bash
# Initialize Terraform or update to latest by provider.tf `terraform init -upgrade`
terraform init

# Preview changes
terraform plan

# Apply changes
terraform apply
```

## Usage

After deployment, you can invoke the Lambda function:

```bash
aws lambda invoke \
  --function-name dev-aws-data-collector-collector \
  --cli-binary-format raw-in-base64-out \
  --payload '{"id":"test-1","data":{"message":"Hello World"}}' \
  response.json

cat response.json
```

## Cost Optimization Features

- **Lambda**: 128MB memory (minimum), charged per 100ms execution
- **DynamoDB**: Pay-per-request billing (no minimum costs when idle)
- **CloudWatch Logs**: 7-day retention to minimize storage costs
- **No always-on infrastructure**: All services scale to zero when not in use

## Development

### Project Structure

```
.
├── providers.tf              # Terraform provider configuration
├── variables.tf              # Input variables
├── main.tf                   # Main infrastructure resources
├── outputs.tf                # Output values
├── terraform.tfvars.example  # Example variables (safe to commit)
├── lambda/                   # Lambda function source code
│   └── index.py             # Lambda handler
└── .env.example             # Example environment variables
```

### Destroy Infrastructure

To tear down all resources:

```bash
terraform destroy
```

## Security

- Never commit `.tfvars`, `.env`, or `.terraform/` to version control
- Use AWS Secrets Manager or Parameter Store for sensitive data in production
- Follow least-privilege IAM principles

## License

MIT
