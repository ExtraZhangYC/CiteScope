#!/usr/bin/env python3
"""
快速启动API服务器脚本
"""
import os
import sys

# 加载环境变量
try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed, skipping .env file")

# 启动Flask应用
if __name__ == '__main__':
    # 兼容两种入口：app.py 里既有 create_app()，也可能顶层有 app 实例。
    from app import create_app
    app = create_app()

    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    host = os.getenv('HOST', '0.0.0.0')

    print(f"""
    ========================================
    Citation Analysis API Server
    ========================================
    Starting server on http://{host}:{port}
    Debug mode: {debug}
    ========================================
    """)

    app.run(host=host, port=port, debug=debug, use_reloader=False)








