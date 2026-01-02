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
- AWS CLI configured with credentials
- Docker (for building Lambda layers with ARM64 architecture, in your case maybe x86-64)
- Google Gemini API key

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
### 2. Configure Terraform Variables

Create `terraform.tfvars`:

```bash
cat > terraform.tfvars <<EOF
environment     = "dev"
project_name    = "aws-data-collector"
openai_api_key  = "your-gemini-api-key-here"
EOF
```

**Important**: `terraform.tfvars` contains sensitive data and is excluded from version control.

Edit `terraform.tfvars` with your desired configuration.

### 3. Deploy Infrastructure

```bash
# Initialize Terraform or update to latest by provider.tf `terraform init -upgrade`
terraform init

# Preview changes
terraform plan

# Deploy
terraform apply

## Usage

### Manual Invocation

Trigger news collection manually:

```bash
# Trigger dispatcher
aws lambda invoke \
  --function-name dev-aws-data-collector-dispatcher \
  response.json

# Trigger URL collector directly
aws lambda invoke \
  --function-name dev-aws-data-collector-collector \
  --cli-binary-format raw-in-base64-out \
  --payload '{"category_id":"CAAqJQgKIh9DQkFTRVFvSUwyMHZNREpmTjNRU0JYcG9MVlJYS0FBUAE"}' \
  response.json

# Trigger chart generator (async invocation to enable Destinations)
aws lambda invoke \
  --function-name dev-aws-data-collector-chart-generator \
  --invocation-type Event \
  --cli-binary-format raw-in-base64-out \
  --payload '{"trend_id": "trend-14d-20251227-081625"}' \
  response.json

# Trigger static website generator directly
aws lambda invoke \
  --function-name dev-aws-data-collector-static-website-generator \
  --cli-binary-format raw-in-base64-out \
  --payload '{"trend_id": "trend-14d-20251227-081625"}' \
  response.json


### Query Results

```bash
# Scan DynamoDB for collected news
aws dynamodb scan \
  --table-name dev-aws-data-collector-news-urls \
  --max-items 10

# Check batch processing status
aws dynamodb scan \
  --table-name dev-aws-data-collector-batch-requests
```

## AI Analysis Output

Each news article is analyzed for:

1. **Industries**: Related industry domains with impact assessment
   - `domain`: Industry name (e.g., "半導體", "電動車", "金融")
   - `impact_score`: Rating from -5 (very negative) to +5 (very positive)
   - `reason`: Explanation of the impact

2. **Genre**: News type (e.g., "快訊", "深度報導", "財報", "分析評論")

## Cost Optimization Features

- **Lambda ARM64**: Graviton processors provide 20% better price-performance
- **Gemini API**: Free tier for experimental thinking mode
- **DynamoDB On-Demand**: Pay-per-request billing (no minimum costs when idle)
- **EventBridge**: First 14 million invocations/month free
- **CloudWatch Logs**: 7-day retention to minimize storage costs
- **No always-on infrastructure**: All services scale to zero when not in use

### Estimated Monthly Cost

Based on collecting 10 news articles/day:

| Service | Monthly Cost |
|---------|--------------||
| Lambda (ARM64) | ~$0.02 |
| DynamoDB | ~$0.05 |
| Secrets Manager | $0.40 |
| CloudWatch Logs | ~$0.03 |
| Gemini API (experimental) | $0.00 |
| **Total** | **~$0.50/month** |

**Cost Optimization Tip**: Replace Secrets Manager with SSM Parameter Store to save $0.40/month (reduce to $0.16/month)

## Development

### Project Structure

```
.
├── providers.tf                      # AWS provider configuration
├── variables.tf                      # Input variables
├── main.tf                           # Secrets Manager resources
├── dynamodb.tf                       # DynamoDB tables
├── iam.tf                            # IAM roles and policies
├── lambda_dispatcher.tf              # Dispatcher Lambda + EventBridge
├── lambda_get_news_urls.tf          # URL collector Lambda
├── lambda_get_news_content.tf       # Content collector Lambda
├── lambda_process_batch_results.tf  # Batch processor Lambda + EventBridge
├── outputs.tf                        # Output values
├── lambda/
│   ├── dispatcher/                  # Hourly trigger handler
│   ├── get_news_urls/              # Google News RSS collector
│   └── get_news_content/           # Article content extractor + Gemini analysis
└── .github/
    └── copilot-instructions.md     # AI agent development guidelines
```

### Lambda Layers

Each Lambda function uses Docker to build ARM64-compatible layers:
- Dependencies are installed using `public.ecr.aws/lambda/python:3.13`
- Built with `--platform linux/arm64` for Graviton processors
- Automatically rebuilt when `requirements.txt` changes

### Data Flow

```
EventBridge (hourly)
    ↓
Dispatcher Lambda
    ↓
Get News URLs Lambda → DynamoDB (news-urls)
    ↓ (SQS queue for each new URL)
Get News Content Lambda → Gemini API (immediate analysis)
    ↓
DynamoDB (news-urls with analysis)
```

### Destroy Infrastructure

To tear down all resources:

```bash
terraform destroy
```

## Security

- Never commit `terraform.tfvars`, `.env`, or `.terraform/` to version control
- Gemini API key stored in AWS Secrets Manager with encryption
- DynamoDB tables use server-side encryption
- Point-in-time recovery enabled for data protection
- IAM roles follow least-privilege principles
- Lambda functions use separate IAM roles per function type

## Monitoring

- CloudWatch Logs available for all Lambda functions (7-day retention)
- DynamoDB Point-in-Time Recovery enabled
- Batch processing tracked in `batch-requests` table

## Troubleshooting

### Docker Build Issues

If you encounter `docker pull denied`:

```bash
docker logout public.ecr.aws
aws ecr-public get-login-password | docker login --username AWS --password-stdin public.ecr.aws
```

### Check Lambda Logs

```bash
aws logs tail /aws/lambda/dev-aws-data-collector-collector --follow
aws logs tail /aws/lambda/dev-aws-data-collector-content-collector --follow
aws logs tail /aws/lambda/dev-aws-data-collector-batch-processor --follow
```

## License

MIT
