"""
基于 token 的认证装饰器（类似 flask_jwt_extended 的 jwt_required / get_jwt_identity）
从请求头 Authorization: Bearer <token> 或查询参数 token= 读取 token，
校验通过后设置 g.user_id、g.current_user，供视图使用。
"""

from functools import wraps
from flask import g, request
from model.user_model import UserModel
from utils.response import make_response

_user_model = None


def _get_user_model():
    global _user_model
    if _user_model is None:
        _user_model = UserModel()
    return _user_model


def _get_token_from_request():
    """从请求头或查询参数获取 token"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.args.get("token")


def token_required(f):
    """
    装饰器：校验请求中的 token，过期或无效则返回 401。
    校验通过后设置 g.user_id、g.current_user，视图内可用 get_current_user_id() 获取当前用户 id。
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_request()
        if not token:
            return make_response(False, 401, "token is required", None)
        user_model = _get_user_model()
        user = user_model.get_user_by_token(token)
        if not user:
            return make_response(False, 401, "invalid or expired token", None)
        g.user_id = user["id"]
        g.current_user = user
        return f(*args, **kwargs)

    return decorated


def get_current_user_id():
    """获取当前登录用户 id（需在 @token_required 装饰的视图内使用）"""
    return getattr(g, "user_id", None)


def get_current_user():
    """获取当前登录用户信息（需在 @token_required 装饰的视图内使用）"""
    return getattr(g, "current_user", None)
