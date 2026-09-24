from flask import Flask, send_from_directory, redirect
import os
import sys
import io

# Windows 下让 print() 支持 Unicode（修复 'gbk' 编码错误）
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# 代理配置
_http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
_https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
if _http_proxy:
    os.environ["http_proxy"] = _http_proxy
if _https_proxy:
    os.environ["https_proxy"] = _https_proxy

from flask_cors import CORS
from routes.paper import paper_bp
from routes.analysis import analysis_bp
from routes.health import health_bp
from routes.user import user_bp
from routes.citation import citation_bp
from routes.report import report_bp

# 前端静态文件目录（项目根/client）
CLIENT_DIR = os.path.join(os.path.dirname(__file__), "client")

def create_app():
    app = Flask(__name__, static_folder=CLIENT_DIR, static_url_path="")
    CORS(app)
    app.register_blueprint(paper_bp, url_prefix="/api")
    app.register_blueprint(analysis_bp, url_prefix="/api")
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(citation_bp, url_prefix="/api")
    app.register_blueprint(report_bp, url_prefix="/api")

    # 根路径重定向到前端 index.html
    @app.route("/")
    def index():
        return send_from_directory(CLIENT_DIR, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True,use_reloader=False)
