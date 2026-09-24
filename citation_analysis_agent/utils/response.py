from flask import jsonify

def make_response(success=True, code=200, message="OK", data=None):
    """
    统一的 JSON 返回结构
    """
    return jsonify({
        "code": code,
        "success": success,
        "message": message,
        "data": data
    }), code
