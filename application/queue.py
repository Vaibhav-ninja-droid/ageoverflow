import json
import os
import boto3

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

def enqueue_analysis(request_id, customer_id, urgent=False):
    if not SQS_QUEUE_URL:
        raise RuntimeError("SQS_QUEUE_URL is not set")

    if SQS_QUEUE_URL == "local-disabled":
        raise RuntimeError("SQS is disabled for local mode")

    sqs = boto3.client("sqs", region_name=AWS_REGION)

    sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(
            {
                "request_id": request_id,
                "customer_id": customer_id,
                "urgent": urgent,
            }
        ),
    )