# ===== Panic Common Lambda Layer =====
# Shared panic detection logic between check_panic_signal and check_intraday_panic

# Layer source code archive
data "archive_file" "lambda_panic_common_layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/layer_panic_common"
  output_path = "${path.module}/lambda_panic_common_layer.zip"
}

# Lambda Layer
resource "aws_lambda_layer_version" "panic_common_layer" {
  filename            = data.archive_file.lambda_panic_common_layer_zip.output_path
  layer_name          = "${var.environment}-${var.project_name}-panic-common"
  source_code_hash    = data.archive_file.lambda_panic_common_layer_zip.output_base64sha256
  compatible_runtimes = [var.lambda_runtime]

  description = "Shared panic detection logic (constants, utility functions, panic checks)"
}
