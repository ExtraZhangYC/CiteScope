"""
用户相关路由：注册、登录、验证等
"""

from flask import Blueprint, request
from model.user_model import UserModel
from utils.response import make_response
from utils.auth import token_required, get_current_user_id, get_current_user
from datetime import datetime, timedelta
import secrets
import hashlib

user_bp = Blueprint("user", __name__)
user_model = UserModel()


def generate_token() -> str:
    """生成随机token"""
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    """简单的密码哈希（实际生产环境应使用bcrypt等）"""
    return hashlib.sha256(password.encode()).hexdigest()


# ==================== 用户注册 ====================

@user_bp.route("/users/register", methods=["POST"])
def register():
    """
    用户注册
    请求体: {
        "nickname": "用户昵称",
        "password": "密码",
        "email": "邮箱（可选）",
        "scholar_id": "学者id（可选）"
    }
    """
    data = request.get_json(silent=True) or {}
    
    nickname = data.get("nickname", "").strip()
    password = data.get("password", "").strip()
    email = data.get("email", "").strip() or None
    scholar_id = data.get("scholar_id", "").strip() or None

    # 验证必填字段
    if not nickname:
        return make_response(False, 400, "nickname is required", None)
    
    if not password:
        return make_response(False, 400, "password is required", None)
    
    if len(password) < 6:
        return make_response(False, 400, "password must be at least 6 characters", None)

    # 检查昵称是否已存在（昵称全局唯一）
    existing_user = user_model.get_user_by_nickname(nickname)
    if existing_user:
        return make_response(False, 409, "nickname already exists", None)

    # 检查邮箱是否已存在（如果提供了邮箱）
    if email:
        existing_user = user_model.get_user_by_email(email)
        if existing_user:
            return make_response(False, 409, "email already exists", None)

    # 检查学者id是否已存在（如果提供了学者id）
    if scholar_id:
        existing_user = user_model.get_user_by_scholar_id(scholar_id)
        if existing_user:
            return make_response(False, 409, "scholar_id already exists", None)

    try:
        # 哈希密码
        hashed_password = hash_password(password)
        
        # 创建用户
        user_id = user_model.add_user(
            nickname=nickname,
            password=hashed_password,
            email=email,
            scholar_id=scholar_id
        )

        # 获取创建的用户信息（不返回密码）
        user = user_model.get_user(user_id)
        if user:
            user.pop("password", None)
            user.pop("token", None)
            user.pop("token_expires_at", None)

        return make_response(True, 201, "user registered successfully", {
            "user_id": user_id,
            "user": user
        })
    except Exception as e:
        return make_response(False, 500, f"registration failed: {str(e)}", None)


# ==================== 用户登录 ====================

@user_bp.route("/users/login", methods=["POST"])
def login():
    """
    用户登录（通过昵称 + 密码）
    请求体: {
        "nickname": "用户昵称",
        "password": "密码"
    }
    返回: token和过期时间
    """
    data = request.get_json(silent=True) or {}
    
    nickname = data.get("nickname", "").strip()
    password = data.get("password", "").strip()

    if not nickname:
        return make_response(False, 400, "nickname is required", None)

    if not password:
        return make_response(False, 400, "password is required", None)

    # 根据昵称查找用户（昵称全局唯一）
    user = user_model.get_user_by_nickname(nickname)

    if not user:
        return make_response(False, 401, "user not found", None)

    # 验证密码
    hashed_password = hash_password(password)
    if user.get("password") != hashed_password:
        return make_response(False, 401, "invalid password", None)

    # 生成token（3天过期，过期需重新登录）
    token = generate_token()
    expires_at = datetime.now() + timedelta(days=3)

    # 更新用户token
    user_model.update_token(user.get("id"), token, expires_at)

    # 返回用户信息（不包含密码）
    user_info = dict(user)
    user_info.pop("password", None)
    user_info["token"] = token
    user_info["token_expires_at"] = expires_at.isoformat()

    return make_response(True, 200, "login successful", user_info)


# ==================== 用户验证 ====================

@user_bp.route("/users/verify", methods=["GET"])
@token_required
def verify():
    """
    验证token，获取当前用户信息
    请求头: Authorization: Bearer <token>
    或查询参数: ?token=<token>
    """
    user_info = dict(get_current_user())
    user_info.pop("password", None)
    user_info.pop("token", None)
    if user_info.get("token_expires_at") and isinstance(user_info["token_expires_at"], datetime):
        user_info["token_expires_at"] = user_info["token_expires_at"].isoformat()
    return make_response(True, 200, "token is valid", user_info)


# ==================== 用户登出 ====================

@user_bp.route("/users/logout", methods=["POST"])
@token_required
def logout():
    """
    用户登出，清除token
    请求头: Authorization: Bearer <token>
    """
    user_model.clear_token(get_current_user_id())
    return make_response(True, 200, "logout successful", None)


# ==================== 用户CRUD ====================

@user_bp.route("/users", methods=["POST"])
def add_user():
    """
    添加用户（管理员功能，直接创建用户）
    请求体: {
        "nickname": "用户昵称",
        "password": "密码",
        "email": "邮箱（可选）",
        "scholar_id": "学者id（可选）"
    }
    """
    data = request.get_json(silent=True) or {}
    
    nickname = data.get("nickname", "").strip()
    password = data.get("password", "").strip()
    email = data.get("email", "").strip() or None
    scholar_id = data.get("scholar_id", "").strip() or None

    if not nickname or not password:
        return make_response(False, 400, "nickname and password are required", None)

    try:
        hashed_password = hash_password(password)
        user_id = user_model.add_user(
            nickname=nickname,
            password=hashed_password,
            email=email,
            scholar_id=scholar_id
        )

        user = user_model.get_user(user_id)
        if user:
            user.pop("password", None)

        return make_response(True, 201, "user created successfully", {
            "user_id": user_id,
            "user": user
        })
    except Exception as e:
        return make_response(False, 500, f"create user failed: {str(e)}", None)


@user_bp.route("/users/<int:user_id>", methods=["GET"])
@token_required
def get_user(user_id):
    """
    根据id获取用户信息（仅能查看自己）
    """
    if user_id != get_current_user_id():
        return make_response(False, 403, "forbidden", None)
    user = user_model.get_user(user_id)
    if not user:
        return make_response(False, 404, "user not found", None)

    # 不返回密码
    user_info = dict(user)
    user_info.pop("password", None)
    
    # 转换token_expires_at为字符串
    if user_info.get("token_expires_at") and isinstance(user_info["token_expires_at"], datetime):
        user_info["token_expires_at"] = user_info["token_expires_at"].isoformat()

    return make_response(True, 200, "success", user_info)


@user_bp.route("/users/me", methods=["GET"])
@token_required
def get_current_user_info():
    """获取当前登录用户信息"""
    user_info = dict(get_current_user())
    user_info.pop("password", None)
    user_info.pop("token", None)
    if user_info.get("token_expires_at") and isinstance(user_info["token_expires_at"], datetime):
        user_info["token_expires_at"] = user_info["token_expires_at"].isoformat()
    return make_response(True, 200, "success", user_info)


@user_bp.route("/users/me", methods=["PUT"])
@token_required
def update_current_user():
    user_id = get_current_user_id()
    user = user_model.get_user(user_id)
    if not user:
        return make_response(False, 404, "user not found", None)

    data = request.get_json(silent=True) or {}
    allowed_fields = ["nickname", "email", "scholar_id", "password"]
    update_data = {}

    for field in allowed_fields:
        if field in data:
            value = data[field]
            if isinstance(value, str):
                value = value.strip() or None
            if field == "password" and value:
                value = hash_password(value)
            update_data[field] = value

    if not update_data:
        return make_response(False, 400, "no valid fields to update", None)

    if "nickname" in update_data and update_data["nickname"]:
        existing_user = user_model.get_user_by_nickname(update_data["nickname"])
        if existing_user and existing_user.get("id") != user_id:
            return make_response(False, 409, "nickname already exists", None)
    if "email" in update_data and update_data["email"]:
        existing_user = user_model.get_user_by_email(update_data["email"])
        if existing_user and existing_user.get("id") != user_id:
            return make_response(False, 409, "email already exists", None)
    if "scholar_id" in update_data and update_data["scholar_id"]:
        existing_user = user_model.get_user_by_scholar_id(update_data["scholar_id"])
        if existing_user and existing_user.get("id") != user_id:
            return make_response(False, 409, "scholar_id already exists", None)

    try:
        success = user_model.update_user(user_id, **update_data)
        if not success:
            return make_response(False, 500, "update failed", None)
        updated_user = user_model.get_user(user_id)
        if updated_user:
            updated_user.pop("password", None)
            if updated_user.get("token_expires_at") and isinstance(updated_user["token_expires_at"], datetime):
                updated_user["token_expires_at"] = updated_user["token_expires_at"].isoformat()
        return make_response(True, 200, "user updated successfully", updated_user)
    except Exception as e:
        return make_response(False, 500, f"update failed: {str(e)}", None)


@user_bp.route("/users/<int:user_id>", methods=["PUT"])
@token_required
def update_user(user_id):
    """
    更新用户信息（仅能更新自己）
    请求体: {
        "nickname": "新昵称（可选）",
        "email": "新邮箱（可选）",
        "scholar_id": "新学者id（可选）",
        "password": "新密码（可选）"
    }
    """
    if user_id != get_current_user_id():
        return make_response(False, 403, "forbidden", None)
    user = user_model.get_user(user_id)
    if not user:
        return make_response(False, 404, "user not found", None)

    data = request.get_json(silent=True) or {}
    
    # 过滤允许更新的字段
    allowed_fields = ["nickname", "email", "scholar_id", "password"]
    update_data = {}
    
    for field in allowed_fields:
        if field in data:
            value = data[field]
            if isinstance(value, str):
                value = value.strip() or None
            if field == "password" and value:
                # 哈希新密码
                value = hash_password(value)
            update_data[field] = value

    if not update_data:
        return make_response(False, 400, "no valid fields to update", None)

    # 检查昵称是否已被其他用户使用
    if "nickname" in update_data and update_data["nickname"]:
        existing_user = user_model.get_user_by_nickname(update_data["nickname"])
        if existing_user and existing_user.get("id") != user_id:
            return make_response(False, 409, "nickname already exists", None)

    # 检查邮箱是否已被其他用户使用
    if "email" in update_data and update_data["email"]:
        existing_user = user_model.get_user_by_email(update_data["email"])
        if existing_user and existing_user.get("id") != user_id:
            return make_response(False, 409, "email already exists", None)

    # 检查学者id是否已被其他用户使用
    if "scholar_id" in update_data and update_data["scholar_id"]:
        existing_user = user_model.get_user_by_scholar_id(update_data["scholar_id"])
        if existing_user and existing_user.get("id") != user_id:
            return make_response(False, 409, "scholar_id already exists", None)

    try:
        success = user_model.update_user(user_id, **update_data)
        if not success:
            return make_response(False, 500, "update failed", None)

        # 返回更新后的用户信息
        updated_user = user_model.get_user(user_id)
        if updated_user:
            updated_user.pop("password", None)
            if updated_user.get("token_expires_at") and isinstance(updated_user["token_expires_at"], datetime):
                updated_user["token_expires_at"] = updated_user["token_expires_at"].isoformat()

        return make_response(True, 200, "user updated successfully", updated_user)
    except Exception as e:
        return make_response(False, 500, f"update failed: {str(e)}", None)


@user_bp.route("/users/<int:user_id>", methods=["DELETE"])
@token_required
def delete_user(user_id):
    """
    删除用户（仅能删除自己）
    """
    if user_id != get_current_user_id():
        return make_response(False, 403, "forbidden", None)
    user = user_model.get_user(user_id)
    if not user:
        return make_response(False, 404, "user not found", None)

    try:
        success = user_model.delete_user(user_id)
        if not success:
            return make_response(False, 500, "delete failed", None)

        return make_response(True, 200, "user deleted successfully", None)
    except Exception as e:
        return make_response(False, 500, f"delete failed: {str(e)}", None)


@user_bp.route("/users", methods=["GET"])
@token_required
def list_users():
    """
    获取所有用户列表（需登录）
    """
    try:
        users = user_model.list_users()
        
        # 移除密码和敏感信息
        for user in users:
            user.pop("password", None)
            if user.get("token_expires_at") and isinstance(user["token_expires_at"], datetime):
                user["token_expires_at"] = user["token_expires_at"].isoformat()

        return make_response(True, 200, "success", users)
    except Exception as e:
        return make_response(False, 500, f"list users failed: {str(e)}", None)
