from multiprocessing import pool
import os
import redis
import logging


logger = logging.getLogger(__name__)

# 환경 변수에서 값 불러오기
REDIS_HOST = os.environ.get("REDIS_HOST")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
REDIS_PORT = os.environ.get("REDIS_PORT", 6380)
REDIS_SSL = os.environ.get("REDIS_SSL", "true").lower() == "true"

redis_client = None
if REDIS_HOST and REDIS_PASSWORD:
    try:
        pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=int(REDIS_PORT),
            password=REDIS_PASSWORD,
            ssl=REDIS_SSL,
            decode_responses=True
        )
        redis_client = redis.Redis(connection_pool=pool)
        redis_client.ping()
        logging.info("Successfully connected to Redis.")
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
else:
    logging.warning("Redis connection details not found in environment variables. Simulator will not push to Redis.")

# 클라이언트 인스턴스
