# all my end points

from flask import Blueprint, jsonify, request
from application.db import get_requests_by_customer, create_request, health_db, get_requests_by_customer_and_id, request_success, request_failed, get_stat_db, customer_exist, get_users_by_customer, get_user_by_customer_and_user_id
import uuid
import json
import os
from datetime import datetime, timezone
from application.queue import enqueue_analysis

api = Blueprint("api", __name__, url_prefix="/api/v1")

VALID_STATUSES = {"pending", "success", "failed"}
VALID_GENERATIONS = {"silent", "baby_boomers", "x", "y", "z", "alpha"}

def is_valid_uuid(value):
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False

def is_valid_uuid_v4(value):
    try:
        val = uuid.UUID(value, version=4)
    except ValueError:
        return False
    return str(val) == value.lower()

def is_valid_rfc3339(value):
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

def now_rfc3339():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def mean(x):
    if not x:
        return 0
    return sum(x) / len(x)

def median(x):
    if not x:
        return 0
    sorted_x = sorted(x)
    n = len(sorted_x)
    middle = n // 2

    if n % 2 == 1:
        return sorted_x[middle]
    
    return (sorted_x[middle - 1] + sorted_x[middle]) / 2

def buckets(x): 
    b = {"20" : 0, "30" : 0, "40" : 0, "50" : 0, "60" : 0, "70" : 0, "80" : 0}

    for i in x:
        if i < 30:
            b["20"] += 1
        elif i < 40:
            b["30"] += 1
        elif i < 50:
            b["40"] += 1
        elif i < 60:
            b["50"] += 1
        elif i < 70:
            b["60"] += 1
        elif i < 80:
            b["70"] += 1
        else:
            b["80"] += 1
    
    return b

def serialise_request(row):
    item = {
        "id": row["id"],
        "user_id": row["user_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "status": row["status"],
    }

    if row["status"] == "success":
        item["result"] = {
            "checksum": row["checksum"],
            "generations": {
                "silent": row["silent"],
                "baby_boomers": row["baby_boomers"],
                "x": row["x"],
                "y": row["y"],
                "z": row["z"],
                "alpha": row["alpha"],
            },
            "primary_generation": row["primary_generation"],
            "age": row["age"],
        }
    else:
        item["result"] = None

    return item

# GET /analysis/{customer_id}/requests
@api.route("/analysis/<customer_id>/requests", methods=["GET"])
def list_requests(customer_id):
    try:
        if not is_valid_uuid_v4(customer_id):
            return jsonify({"error": "invalid customer_id"}), 400

        limit_raw = request.args.get("limit", "100")
        offset_raw = request.args.get("offset", "0")
        start = request.args.get("start")
        end = request.args.get("end")
        user_id = request.args.get("user_id")
        status = request.args.get("status")
        generation = request.args.get("generation")

        try:
            limit = int(limit_raw)
            if limit <= 0 or limit > 1000:
                raise ValueError
        except ValueError:
            return jsonify({"error": "invalid limit"}), 400

        try:
            offset = int(offset_raw)
            if offset < 0:
                raise ValueError
        except ValueError:
            return jsonify({"error": "invalid offset"}), 400

        if start is not None and not is_valid_rfc3339(start):
            return jsonify({"error": "invalid start"}), 400

        if end is not None and not is_valid_rfc3339(end):
            return jsonify({"error": "invalid end"}), 400

        if user_id is not None and not is_valid_uuid(user_id):
            return jsonify({"error": "invalid user_id"}), 400

        if status is not None and status not in VALID_STATUSES:
            return jsonify({"error": "invalid status"}), 400

        if generation is not None and generation not in VALID_GENERATIONS:
            return jsonify({"error": "invalid generation"}), 400

        rows = get_requests_by_customer(
            customer_id=customer_id,
            limit=limit,
            offset=offset,
            start=start,
            end=end,
            user_id=user_id,
            status=status,
            generation=generation,
        )

        return jsonify([serialise_request(row) for row in rows]), 200
    except Exception as e:
        return jsonify({"error": "internal server error"}), 500

# POST /analysis/{customer_id}/requests
@api.route("/analysis/<customer_id>/requests", methods=["POST"])
def submit_request(customer_id):
    try:
        if not is_valid_uuid_v4(customer_id):
            return jsonify({"error": "invalid customer_id"}), 400
        
        if not request.is_json:
            return jsonify({"error": "request body must be json"}), 400

        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "invalid json"}), 400

        user_id = body.get("user_id")
        urgent = body.get("urgent")
        photos = body.get("photos")

        if user_id is None or not isinstance(user_id, str) or not is_valid_uuid(user_id):
            return jsonify({"error": "invalid user_id"}), 400

        if not isinstance(urgent, bool):
            return jsonify({"error": "invalid urgent"}), 400

        if not isinstance(photos, list) or len(photos) == 0:
            return jsonify({"error": "invalid photos"}), 400

        if not all(isinstance(photo, str) for photo in photos):
            return jsonify({"error": "invalid photos"}), 400

        request_id = str(uuid.uuid4())
        timestamp = now_rfc3339()

        row = create_request(
            customer_id=customer_id, 
            request_id=request_id, 
            user_id=user_id, 
            created_at=timestamp, 
            updated_at=timestamp, 
            urgent=urgent, 
            photos=photos
        )

        try:
            enqueue_analysis(request_id=request_id, customer_id=customer_id, urgent=urgent)
        except Exception as error:
            print(f"SQS enqueue failed for request {request_id}: {error}", flush=True)
            request_failed(request_id, now_rfc3339())
            return jsonify({"error": "failed to enqueue analysis"}), 500

        return jsonify(serialise_request(row)), 201

    except Exception as e:
        return jsonify({"error": "internal server error"}), 500

# GET /health
@api.route("/health", methods=["GET"])
def health():
    if health_db():
        return jsonify({"status": "healthy"}), 200
    
    return jsonify({"status": "nothealthy"}), 503

# GET /analysis/{customer_id}/requests/{request_id}
@api.route("/analysis/<customer_id>/requests/<request_id>", methods=["GET"])
def get_request(customer_id, request_id):
    try:
        if not is_valid_uuid_v4(customer_id):
            return jsonify({"error": "invalid customer_id"}), 400

        if not is_valid_uuid(request_id):
            return jsonify({"error": "invalid request_id"}), 400

        row = get_requests_by_customer_and_id(customer_id, request_id)

        if row is None:
            return jsonify({"error": "request not found"}), 404

        return jsonify(serialise_request(row)), 200
    except Exception as e:
        return jsonify({"error": "internal server error"}), 500

# GET /analysis/{customer_id}/statistics
@api.route("/analysis/<customer_id>/statistics", methods=["GET"])
def get_stats(customer_id):
    try:
        if not is_valid_uuid_v4(customer_id):
            return jsonify({"error": "invalid customer_id"}), 400
        
        if not customer_exist(customer_id):
            return jsonify({"error": "customer not found"}), 404

        t, ar = get_stat_db(customer_id)
        ages = [row["age"] for row in ar]

        response = {
            "generated_at": now_rfc3339(),
            "contents": {
                "total_users": t["total_users"],
                "total_requests": t["total_requests"],
                "mean": mean(ages),
                "median": median(ages),
                "buckets": buckets(ages),
            },
        }
        return jsonify(response), 200
    except Exception as e:
        return jsonify({"error": "internal server error"}), 500

# GET /analysis/{customer_id}/users
@api.route("/analysis/<customer_id>/users", methods=["GET"])
def list_users(customer_id):
    try:
        if not is_valid_uuid_v4(customer_id):
            return jsonify({"error": "invalid customer_id"}), 400

        limit_raw = request.args.get("limit", "100")
        offset_raw = request.args.get("offset", "0")

        try:
            limit = int(limit_raw)
            if limit <= 0 or limit > 1000:
                raise ValueError
        except ValueError:
            return jsonify({"error": "invalid limit"}), 400

        try:
            offset = int(offset_raw)
            if offset < 0:
                raise ValueError
        except ValueError:
            return jsonify({"error": "invalid offset"}), 400

        users = get_users_by_customer(customer_id, limit=limit, offset=offset)
        return jsonify(users), 200
    except Exception as e:
        return jsonify({"error": "internal server error"}), 500

# GET /analysis/{customer_id}/users/{user_id}
@api.route("/analysis/<customer_id>/users/<user_id>", methods=["GET"])
def get_user(customer_id, user_id):
    try:
        if not is_valid_uuid_v4(customer_id):
            return jsonify({"error": "invalid customer_id"}), 400

        if not is_valid_uuid(user_id):
            return jsonify({"error": "invalid user_id"}), 400

        user = get_user_by_customer_and_user_id(customer_id, user_id)

        if user is None:
            return jsonify({"error": "user not found"}), 404

        return jsonify(user), 200
    except Exception as e:
        return jsonify({"error": "internal server error"}), 500