terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.5"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# 1. Variables

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "app_name" {
  type    = string
  default = "ageoverflow"
}

variable "app_port" {
  type    = number
  default = 8080
}

variable "instance_type" {
  type    = string
  default = "t2.micro"
}

variable "db_name" {
  type    = string
  default = "ageoverflow"
}

variable "db_username" {
  type    = string
  default = "postgres"
}

variable "db_password" {
  type      = string
  sensitive = true
}

# 2. Networking

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# 3. Amazon Linux 2023 AMI

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# 4. Security Groups

resource "aws_security_group" "alb_sg" {
  name        = "${var.app_name}-alb-sg-${random_id.bucket_suffix.hex}"
  description = "Security group for the public load balancer"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Allow HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "api_sg" {
  name        = "${var.app_name}-api-sg-${random_id.bucket_suffix.hex}"
  description = "Security group for API instances"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Allow API traffic only from load balancer"
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  ingress {
    description = "Allow SSH for debugging"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "worker_sg" {
  name        = "${var.app_name}-worker-sg-${random_id.bucket_suffix.hex}"
  description = "Security group for worker instances"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Allow SSH for debugging"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db_sg" {
  name        = "${var.app_name}-db-sg-${random_id.bucket_suffix.hex}"
  description = "Security group for AgeOverflow database"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Allow PostgreSQL from API instances"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api_sg.id]
  }

  ingress {
    description     = "Allow PostgreSQL from worker instances"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.worker_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 5. RDS

resource "aws_db_subnet_group" "ageoverflow_db_subnets" {
  name       = "${var.app_name}-db-subnets-${random_id.bucket_suffix.hex}"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "ageoverflow_db" {
  identifier              = "${var.app_name}-db-${random_id.bucket_suffix.hex}"
  allocated_storage       = 20
  max_allocated_storage   = 1000
  engine                  = "postgres"
  engine_version          = "17"
  instance_class          = "db.t3.micro"
  db_name                 = var.db_name
  username                = var.db_username
  password                = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.ageoverflow_db_subnets.name
  vpc_security_group_ids  = [aws_security_group.db_sg.id]
  publicly_accessible     = true
  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = 0

  tags = {
    Name = "${var.app_name}-db"
  }
}

resource "aws_sqs_queue" "analysis_queue" {
  name                       = "${var.app_name}-analysis-queue-${random_id.bucket_suffix.hex}"
  visibility_timeout_seconds = 240
  message_retention_seconds  = 86400
}

# 6. Package app files into a zip

data "archive_file" "app_bundle" {
  type        = "zip"
  output_path = "${path.module}/app_bundle.zip"

  source {
    content  = file("${path.module}/Dockerfile")
    filename = "Dockerfile"
  }

  source {
    content  = file("${path.module}/pyproject.toml")
    filename = "pyproject.toml"
  }

  source {
    content  = file("${path.module}/application/__init__.py")
    filename = "application/__init__.py"
  }

  source {
    content  = file("${path.module}/application/db.py")
    filename = "application/db.py"
  }

  source {
    content  = file("${path.module}/application/routes.py")
    filename = "application/routes.py"
  }

  source {
    content  = file("${path.module}/application/engine.py")
    filename = "application/engine.py"
  }

  source {
    content  = file("${path.module}/application/queue.py")
    filename = "application/queue.py"
  }

  source {
    content  = file("${path.module}/application/worker.py")
    filename = "application/worker.py"
  }

  source {
    content  = file("${path.module}/poetry.lock")
    filename = "poetry.lock"
  }
}

# 7. S3 bucket to hold app bundle

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "app_bundle_bucket" {
  bucket        = "${var.app_name}-bundle-${random_id.bucket_suffix.hex}"
  force_destroy = true
}

resource "aws_s3_object" "app_bundle" {
  bucket = aws_s3_bucket.app_bundle_bucket.id
  key    = "app_bundle.zip"
  source = data.archive_file.app_bundle.output_path
  etag   = filemd5(data.archive_file.app_bundle.output_path)
}

# 8. IAM role for EC2 to read from S3
data "aws_iam_instance_profile" "lab" {
  name = "LabInstanceProfile"
}

# 9. Locals

locals {
  database_url = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.ageoverflow_db.address}:5432/${var.db_name}"
}

# 10. Common startup script

locals {
  common_bootstrap = <<-EOF
    #!/bin/bash
    set -euxo pipefail

    exec > >(tee /var/log/user-data.log | logger -t user-data) 2>&1

    dnf update -y
    dnf install -y docker unzip awscli

    systemctl enable docker
    systemctl start docker

    mkdir -p /opt/ageoverflow
    cd /opt/ageoverflow

    aws s3 cp s3://${aws_s3_bucket.app_bundle_bucket.id}/${aws_s3_object.app_bundle.key} /opt/ageoverflow/app_bundle.zip

    rm -rf /opt/ageoverflow/app
    unzip -o /opt/ageoverflow/app_bundle.zip -d /opt/ageoverflow/app

    cd /opt/ageoverflow/app
    docker build -t ageoverflow-api .

    db_ready=0
    for i in $(seq 1 60); do
      if bash -c "</dev/tcp/${aws_db_instance.ageoverflow_db.address}/5432" 2>/dev/null; then
        db_ready=1
        break
      fi
      sleep 10
    done

    if [ "$db_ready" -ne 1 ]; then
      echo "Database was not ready"
      exit 1
    fi
  EOF
}

# 11. application Load Balancer

resource "aws_lb" "api_lb" {
  name               = "${var.app_name}-alb-${random_id.bucket_suffix.hex}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "api_tg" {
  name        = "${var.app_name}-tg-${random_id.bucket_suffix.hex}"
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path                = "/api/v1/health"
    port                = tostring(var.app_port)
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 15
    matcher             = "200"
  }
}

resource "aws_lb_listener" "api_listener" {
  load_balancer_arn = aws_lb.api_lb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api_tg.arn
  }
}

# 12. API launch template and autoscaling group

resource "aws_launch_template" "api" {
  name_prefix   = "${var.app_name}-api-"
  image_id      = data.aws_ami.amazon_linux_2023.id
  instance_type = var.instance_type

  iam_instance_profile {
    name = data.aws_iam_instance_profile.lab.name
  }

  vpc_security_group_ids = [aws_security_group.api_sg.id]

  user_data = base64encode(<<-EOF
${local.common_bootstrap}

docker rm -f ageoverflow-api-container || true

docker run -d \
  --name ageoverflow-api-container \
  --restart unless-stopped \
  -p ${var.app_port}:8080 \
  -e DATABASE_URL='${local.database_url}' \
  -e SQS_QUEUE_URL='${aws_sqs_queue.analysis_queue.url}' \
  -e AWS_REGION='${var.aws_region}' \
  ageoverflow-api
EOF
  )
}

resource "aws_autoscaling_group" "api" {
  name                = "${var.app_name}-api-asg-${random_id.bucket_suffix.hex}"
  min_size            = 1
  desired_capacity    = 1
  max_size            = 3
  vpc_zone_identifier = data.aws_subnets.default.ids
  target_group_arns   = [aws_lb_target_group.api_tg.arn]
  health_check_type   = "ELB"

  launch_template {
    id      = aws_launch_template.api.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${var.app_name}-api"
    propagate_at_launch = true
  }

  depends_on = [
    aws_db_instance.ageoverflow_db,
    aws_s3_object.app_bundle,
    aws_lb_listener.api_listener
  ]
}

resource "aws_autoscaling_policy" "api_cpu_target" {
  name                   = "${var.app_name}-api-cpu-target"
  autoscaling_group_name = aws_autoscaling_group.api.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }

    target_value = 40
  }
}

# 13. worker launch template and autoscaling group

resource "aws_launch_template" "worker" {
  name_prefix   = "${var.app_name}-worker-"
  image_id      = data.aws_ami.amazon_linux_2023.id
  instance_type = var.instance_type

  iam_instance_profile {
    name = data.aws_iam_instance_profile.lab.name
  }

  vpc_security_group_ids = [aws_security_group.worker_sg.id]

  user_data = base64encode(<<-EOF
${local.common_bootstrap}

docker rm -f ageoverflow-worker-container || true

docker run -d \
  --name ageoverflow-worker-container \
  --restart unless-stopped \
  -e DATABASE_URL='${local.database_url}' \
  -e SQS_QUEUE_URL='${aws_sqs_queue.analysis_queue.url}' \
  -e AWS_REGION='${var.aws_region}' \
  ageoverflow-api \
  pipx run poetry run python -m application.worker
EOF
  )
}

resource "aws_autoscaling_group" "worker" {
  name                = "${var.app_name}-worker-asg-${random_id.bucket_suffix.hex}"
  min_size            = 1
  desired_capacity    = 1
  max_size            = 4
  vpc_zone_identifier = data.aws_subnets.default.ids
  health_check_type   = "EC2"

  launch_template {
    id      = aws_launch_template.worker.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${var.app_name}-worker"
    propagate_at_launch = true
  }

  depends_on = [
    aws_db_instance.ageoverflow_db,
    aws_s3_object.app_bundle,
    aws_sqs_queue.analysis_queue
  ]
}

# 14. worker scaling based on SQS queue depth

resource "aws_autoscaling_policy" "worker_scale_up" {
  name                   = "${var.app_name}-worker-scale-up"
  autoscaling_group_name = aws_autoscaling_group.worker.name
  adjustment_type        = "ChangeInCapacity"
  scaling_adjustment     = 1
  cooldown               = 120
}

resource "aws_autoscaling_policy" "worker_scale_down" {
  name                   = "${var.app_name}-worker-scale-down"
  autoscaling_group_name = aws_autoscaling_group.worker.name
  adjustment_type        = "ChangeInCapacity"
  scaling_adjustment     = -1
  cooldown               = 180
}

resource "aws_cloudwatch_metric_alarm" "queue_has_messages" {
  alarm_name          = "${var.app_name}-queue-has-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 0
  alarm_actions       = [aws_autoscaling_policy.worker_scale_up.arn]

  dimensions = {
    QueueName = aws_sqs_queue.analysis_queue.name
  }
}

resource "aws_cloudwatch_metric_alarm" "queue_empty" {
  alarm_name          = "${var.app_name}-queue-empty"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 6
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 0
  alarm_actions       = [aws_autoscaling_policy.worker_scale_down.arn]

  dimensions = {
    QueueName = aws_sqs_queue.analysis_queue.name
  }
}

# 15. output required by assignment

output "api" {
  value = "http://${aws_lb.api_lb.dns_name}/api/v1/"
}