from flask import Blueprint
from utils.response import make_response
import datetime
import os
import socket
import time
import requests

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """
    健康检查接口
    - 返回当前时间、主机信息、进程信息
    - 尝试访问 Google 判断外网连通性
    """

    # 1️⃣ 基础系统信息
    now = datetime.datetime.utcnow().isoformat() + "Z"
    pid = os.getpid()
    hostname = socket.gethostname()

    # 2️⃣ 网络连通性检测（Google）
    google_check = {
        "reachable": False,
        "status_code": None,
        "latency_ms": None,
        "error": None
    }

    test_url = "https://www.google.com"
    timeout_seconds = 3

    try:
        start_time = time.time()
        resp = requests.get(test_url, timeout=timeout_seconds)
        latency = int((time.time() - start_time) * 1000)

        google_check["reachable"] = resp.status_code == 200
        google_check["status_code"] = resp.status_code
        google_check["latency_ms"] = latency

    except requests.exceptions.Timeout:
        google_check["error"] = f"timeout after {timeout_seconds}s"
    except requests.exceptions.ConnectionError as e:
        google_check["error"] = "connection error"
    except Exception as e:
        google_check["error"] = str(e)

    # 3️⃣ 综合健康状态
    overall_status = google_check["reachable"]

    return make_response(
        success=overall_status,
        code=200 if overall_status else 503,
        message="service healthy" if overall_status else "service unhealthy",
        data={
            "time_utc": now,
            "pid": pid,
            "hostname": hostname,
            "network": {
                "google": google_check
            }
        }
    )
