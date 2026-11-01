import json
import os
import time
import traceback

import boto3

from application.db import (
    init_db,
    get_pending_request_by_id,
    request_success,
    request_failed,
)
from application.engine import run_engine_for_request, validate_engine_output
from application.routes import now_rfc3339

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def process_message(message):
    """
    Process one SQS message.

    The message contains a request_id. The worker fetches the pending request
    from the database, runs the engine, and then updates the database with
    either success or failed.
    """
    body = json.loads(message["Body"])
    request_id = body["request_id"]

    row = get_pending_request_by_id(request_id)

    # sqs can deliver the same message more than once.
    # if this request has already been processed, do nothing.
    if row is None:
        return

    try:
        engine_output = run_engine_for_request(request_id, row["photos"])
        results, generations = validate_engine_output(engine_output)

        request_success(
            request_id=request_id,
            updated_at=now_rfc3339(),
            checksum=results["checksum"],
            primary_generation=results["primary_generation"],
            age=results["age"],
            silent=generations["silent"],
            baby_boomers=generations["baby_boomers"],
            x=generations["x"],
            y=generations["y"],
            z=generations["z"],
            alpha=generations["alpha"],
        )

    except Exception:
        traceback.print_exc()
        request_failed(request_id, now_rfc3339())


def main():
    if not SQS_QUEUE_URL:
        raise RuntimeError("SQS_QUEUE_URL is not set")

    if SQS_QUEUE_URL == "local-disabled":
        raise RuntimeError("SQS is disabled for local mode")

    init_db()

    sqs = boto3.client("sqs", region_name=AWS_REGION)

    while True:
        response = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=240,
        )

        messages = response.get("Messages", [])

        for message in messages:
            try:
                process_message(message)

                # delete only after processing finishs.
                sqs.delete_message(
                    QueueUrl=SQS_QUEUE_URL,
                    ReceiptHandle=message["ReceiptHandle"],
                )

            except Exception:
                # if something unexpected happens here, do not delete the message.
                # sqs will make it visible again after the visibility timeout.
                traceback.print_exc()

        if not messages:
            time.sleep(1)


if __name__ == "__main__":
    main()