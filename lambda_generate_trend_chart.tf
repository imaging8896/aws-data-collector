# ===== Generate Trend Chart Lambda =====

# Lambda function source code archive
# Copy font file before archiving
resource "terraform_data" "copy_font_to_chart_generator" {
    triggers_replace = {
        font_file = filemd5("${path.module}/font/NotoSerifTC-VF.ttf")
    }

    provisioner "local-exec" {
        command = <<EOT
            mkdir -p ${path.module}/lambda/generate_trend_chart
            cp ${path.module}/font/NotoSerifTC-VF.ttf ${path.module}/lambda/generate_trend_chart/
        EOT
    }
}

data "archive_file" "lambda_chart_generator_zip" {
    type        = "zip"
    source_dir  = "${path.module}/lambda/generate_trend_chart"
    output_path = "${path.module}/lambda_chart_generator_function.zip"
    excludes    = ["requirements.txt", "__pycache__"]

    depends_on = [terraform_data.copy_font_to_chart_generator]
}

# Layer 1: NumPy (base dependency)
resource "terraform_data" "install_numpy_layer" {
  triggers_replace = {
    # Trigger rebuild if we change approach
    version = "1"
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/layer_numpy || true
      mkdir -p ${path.module}/layer_numpy/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/layer_numpy/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        bash -c "pip install numpy -t /var/task --upgrade && \
                 find /var/task -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true && \
                 find /var/task -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
                 find /var/task -name '*.pyc' -delete && \
                 find /var/task -name '*.pyo' -delete"
      cd ${path.module}/layer_numpy && zip -r ../lambda_numpy_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "numpy_layer" {
  filename                 = "${path.module}/lambda_numpy_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-numpy"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_numpy_layer.id

  depends_on = [terraform_data.install_numpy_layer]
}

# Layer 2: Matplotlib (excluding numpy)
resource "terraform_data" "install_matplotlib_layer" {
  triggers_replace = {
    # Trigger rebuild if we change approach
    version = "2"
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -f ${path.module}/lambda_matplotlib_layer.zip || true
      rm -rf ${path.module}/layer_matplotlib || true
      mkdir -p ${path.module}/layer_matplotlib/python
      docker run --rm --platform linux/arm64 --entrypoint "" \
        -v "$(pwd)/${path.module}/layer_matplotlib/python:/var/task" \
        public.ecr.aws/lambda/python:${replace(var.lambda_runtime, "python", "")} \
        bash -c "pip install matplotlib --no-deps -t /var/task --upgrade && \
                 pip install pillow contourpy cycler fonttools kiwisolver packaging pyparsing python-dateutil -t /var/task --upgrade && \
                 find /var/task -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true && \
                 find /var/task -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
                 find /var/task -name '*.pyc' -delete && \
                 find /var/task -name '*.pyo' -delete && \
                 find /var/task -type d -name '*.dist-info' -exec rm -rf {} + 2>/dev/null || true && \
                 rm -rf /var/task/numpy 2>/dev/null || true && \
                 rm -rf /var/task/numpy.libs 2>/dev/null || true && \
                 rm -rf /var/task/numpy-*.dist-info 2>/dev/null || true && \
                 rm -rf /var/task/matplotlib/mpl-data/sample_data 2>/dev/null || true && \
                 rm -rf /var/task/matplotlib/tests 2>/dev/null || true"
      cd ${path.module}/layer_matplotlib && zip -r ../lambda_matplotlib_layer.zip python
    EOT
  }
}

resource "aws_lambda_layer_version" "matplotlib_layer" {
  filename                 = "${path.module}/lambda_matplotlib_layer.zip"
  layer_name               = "${var.environment}-${var.project_name}-matplotlib"
  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["arm64"]
  source_code_hash         = terraform_data.install_matplotlib_layer.id

  depends_on = [terraform_data.install_matplotlib_layer]
}

# Lambda Function
resource "aws_lambda_function" "chart_generator" {
  filename         = data.archive_file.lambda_chart_generator_zip.output_path
  function_name    = "${var.environment}-${var.project_name}-chart-generator"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.handler"
  source_code_hash = data.archive_file.lambda_chart_generator_zip.output_base64sha256
  runtime         = var.lambda_runtime
  memory_size     = 256  # Need more memory for matplotlib
  timeout         = 60   # Increased for chart generation
  architectures   = ["arm64"]
  layers          = [
    aws_lambda_layer_version.numpy_layer.arn,
    aws_lambda_layer_version.matplotlib_layer.arn
  ]

  environment {
    variables = {
      DYNAMODB_STATS_TABLE_NAME = aws_dynamodb_table.daily_stats_table.name
      S3_CHART_BUCKET_NAME      = aws_s3_bucket.trend_charts.id
      ENVIRONMENT               = var.environment
      PROJECT_NAME              = var.project_name
      CATEGORIES                = var.categories
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_chart_generator_logs" {
  name              = "/aws/lambda/${aws_lambda_function.chart_generator.function_name}"
  retention_in_days = 7

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Lambda Destination: Trigger static website generator on success
resource "aws_lambda_function_event_invoke_config" "chart_generator_destination" {
  function_name = aws_lambda_function.chart_generator.function_name

  destination_config {
    on_success {
      destination = aws_lambda_function.static_website_generator.arn
    }
  }
}

# Permission for chart generator to invoke static website generator
resource "aws_lambda_permission" "chart_generator_invoke_website" {
  statement_id  = "AllowExecutionFromChartGenerator"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.static_website_generator.function_name
  principal     = "lambda.amazonaws.com"
  source_arn    = aws_lambda_function.chart_generator.arn
}
