from psycopg import connect
from psycopg.rows import dict_row
import json
import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ageoverflow"
)

def get_db_connection():
    return connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    urgent BOOLEAN NOT NULL,
                    photos JSONB NOT NULL,
                    checksum TEXT,
                    primary_generation TEXT,
                    age INTEGER,
                    silent DOUBLE PRECISION,
                    baby_boomers DOUBLE PRECISION,
                    x DOUBLE PRECISION,
                    y DOUBLE PRECISION,
                    z DOUBLE PRECISION,
                    alpha DOUBLE PRECISION
                )
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_requests_customer_created
                ON requests (customer_id, created_at)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_requests_customer_user
                ON requests (customer_id, user_id)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_requests_customer_status
                ON requests (customer_id, status)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_requests_customer_generation
                ON requests (customer_id, primary_generation)
                """
            )

# default values limit = 100, offset = 0, start = None, end = None, user_id = None, status = None, generation = None
def get_requests_by_customer(customer_id, limit=100, offset=0, start=None, end=None, user_id=None, status=None, generation=None):
    query = "SELECT * FROM requests WHERE customer_id = %s"
    params = [customer_id]

    if start is not None:
        query += " AND created_at >= %s"
        params.append(start)

    if end is not None:
        query += " AND created_at < %s"
        params.append(end)

    if user_id is not None:
        query += " AND user_id = %s"
        params.append(user_id)

    if status is not None:
        query += " AND status = %s"
        params.append(status)

    if generation is not None:
        query += " AND primary_generation = %s"
        params.append(generation)

    query += " ORDER BY created_at ASC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()


def create_request(customer_id, request_id, user_id, created_at, updated_at, urgent, photos): 
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO requests (
                    id, customer_id, user_id, created_at, updated_at,
                    status, urgent, photos, checksum, primary_generation,
                    age, silent, baby_boomers, x, y, z, alpha
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    request_id,
                    customer_id,
                    user_id,
                    created_at,
                    updated_at,
                    "pending",
                    urgent,
                    json.dumps(photos),
                    None, None, None, None, None, None, None, None, None,
                ),
            )

            cursor.execute("SELECT * FROM requests WHERE id = %s", (request_id,))
            return cursor.fetchone()

def health_db():
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return True
    except Exception:
        return False

def get_requests_by_customer_and_id(customer_id, request_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM requests WHERE customer_id = %s AND id = %s",
                (customer_id, request_id),
            )
            return cursor.fetchone()

def request_success(request_id, updated_at, checksum, primary_generation, age, silent, baby_boomers, x, y, z, alpha):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE requests
                SET status = %s,
                    updated_at = %s,
                    checksum = %s,
                    primary_generation = %s,
                    age = %s,
                    silent = %s,
                    baby_boomers = %s,
                    x = %s,
                    y = %s,
                    z = %s,
                    alpha = %s
                WHERE id = %s
                """,
                (
                    "success",
                    updated_at,
                    checksum,
                    primary_generation,
                    age,
                    silent,
                    baby_boomers,
                    x,
                    y,
                    z,
                    alpha,
                    request_id,
                ),
            )

            cursor.execute("SELECT * FROM requests WHERE id = %s", (request_id,))
            return cursor.fetchone()

def request_failed(request_id, updated_at):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE requests
                SET status = %s, updated_at = %s
                WHERE id = %s
                """,
                ("failed", updated_at, request_id),
            )

            cursor.execute("SELECT * FROM requests WHERE id = %s", (request_id,))
            return cursor.fetchone()

def get_stat_db(customer_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_requests,
                    COUNT(DISTINCT user_id) AS total_users
                FROM requests
                WHERE customer_id = %s
                """,
                (customer_id,),
            )
            totals = cursor.fetchone()

            cursor.execute(
                """
                SELECT age
                FROM requests
                WHERE customer_id = %s
                  AND status = 'success'
                  AND age IS NOT NULL
                """
                ,
                (customer_id,),
            )
            ages = cursor.fetchall()

            return totals, ages

def customer_exist(customer_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM requests WHERE customer_id = %s LIMIT 1",
                (customer_id,),
            )
            row = cursor.fetchone()
            return row is not None

#helper
def serialise_user_result(row):
    item = {
        "id": row["id"],
        "status": row["status"],
    }

    if row["status"] == "success":
        item["checksum"] = row["checksum"]
        item["primary_generation"] = row["primary_generation"]
        item["age"] = row["age"]

    return item

def get_users_by_customer(customer_id, limit=100, offset=0):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT user_id
                FROM requests
                WHERE customer_id = %s
                ORDER BY user_id ASC
                LIMIT %s OFFSET %s
                """,
                (customer_id, limit, offset),
            )
            user_rows = cursor.fetchall()

            users = []

            for user_row in user_rows:
                user_id = user_row["user_id"]

                cursor.execute(
                    """
                    SELECT id, status, checksum, primary_generation, age
                    FROM requests
                    WHERE customer_id = %s AND user_id = %s
                    ORDER BY created_at ASC
                    """,
                    (customer_id, user_id),
                )
                request_rows = cursor.fetchall()

                users.append(
                    {
                        "id": user_id,
                        "results": [serialise_user_result(row) for row in request_rows],
                    }
                )

            return users

def get_user_by_customer_and_user_id(customer_id, user_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, status, checksum, primary_generation, age
                FROM requests
                WHERE customer_id = %s AND user_id = %s
                ORDER BY created_at ASC
                """,
                (customer_id, user_id),
            )
            request_rows = cursor.fetchall()

            if not request_rows:
                return None

            return {
                "id": user_id,
                "results": [serialise_user_result(row) for row in request_rows],
            }

def get_request_by_id(request_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM requests WHERE id = %s",
                (request_id,),
            )
            return cursor.fetchone()


def get_pending_request_by_id(request_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM requests
                WHERE id = %s AND status = 'pending'
                """,
                (request_id,),
            )
            return cursor.fetchone()