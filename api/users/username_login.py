# -*- coding: utf-8 -*-
"""后台创建的登录用户名。用户名全局唯一，且只有开关打开时才能用来登录。"""
import hashlib
import random
import re

from sqlalchemy import func, inspect, or_, text

from api.users.models import User
from settings.database import engine

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{2,32}$")
PASSWORD_RE = re.compile(r"^(?:[a-zA-Z]{8,}|\d{8,}|(?=.*\d)(?=.*[a-zA-Z])[a-zA-Z\d]{8,})$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")

_columns_ready = False

# 两词相加至少 8 位，读起来像英文单词，比随机串好记。
_NAME_LEFT = (
    "amber", "brave", "bright", "calm", "clear", "crisp", "fresh", "gentle",
    "golden", "happy", "lucky", "quiet", "rapid", "silver", "simple", "smart",
    "sunny", "sweet", "swift", "warm",
)
_NAME_RIGHT = (
    "badger", "beacon", "birch", "brook", "cedar", "cloud", "comet", "daisy",
    "bear", "crow", "deer", "dove", "eagle", "field", "finch", "frog", "garden",
    "harbor", "heron", "island", "lion", "lotus", "lynx", "wolf",
    "maple", "meadow", "otter", "panda", "pebble", "river", "robin", "sparrow",
    "stone", "tiger", "willow",
)
_NAME_TAIL = ("bay", "dale", "glen", "hill", "lake", "moor", "wood")


def memorable_username(extra=0):
    """从 8 位英文组合开始。extra 越大，后面再加一个短词。"""
    name = random.choice(_NAME_LEFT) + random.choice(_NAME_RIGHT)
    if extra > 0:
        name += _NAME_TAIL[(extra - 1) % len(_NAME_TAIL)]
    return name


def is_memorable_username(value):
    text = (value or "").strip().lower()
    if len(text) < 8 or not text.isalpha():
        return False
    for left in _NAME_LEFT:
        if not text.startswith(left):
            continue
        rest = text[len(left):]
        if rest in _NAME_RIGHT:
            return True
        for right in _NAME_RIGHT:
            if rest.startswith(right) and rest[len(right):] in _NAME_TAIL:
                return True
    return False


def generate_memorable_username(db):
    """先试 8 位以上的两词组合，撞名后再加一个短词把用户名变长。"""
    for extra in range(0, len(_NAME_TAIL) + 1):
        for _ in range(24):
            candidate = memorable_username(extra)
            if len(candidate) < 8:
                continue
            if find_user_by_username(db, candidate) or account_conflict(db, candidate):
                continue
            return candidate
    return ""


def normalize_username(raw):
    value = (raw or "").strip()
    if not USERNAME_RE.match(value):
        return "", "用户名需为 2-32 位字母、数字、下划线、中划线或中文"
    return value, ""


def validate_password(raw):
    value = raw or ""
    if not PASSWORD_RE.match(value):
        return "密码需为 8 位及以上字母或数字"
    return ""


def hash_password(raw):
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def store_password(raw):
    """登录接口传来的是 md5。明文则在这里再做一次 md5。"""
    value = (raw or "").strip()
    if re.fullmatch(r"[a-fA-F0-9]{32}", value):
        return value.lower()
    return hash_password(value)


def password_matches(stored, raw):
    value = (raw or "").strip()
    if not value or not stored:
        return False
    if value.lower() == str(stored).lower():
        return True
    return hash_password(value) == str(stored).lower()


def blank_to_none(raw):
    value = (raw or "").strip()
    return value or None


def ensure_username_columns():
    """已有用户表补上用户名和登录开关。多次调用只执行一次。"""
    global _columns_ready
    if _columns_ready:
        return
    statements = (
        "ALTER TABLE tb_user ADD COLUMN username VARCHAR(64) NULL",
        "ALTER TABLE tb_user ADD COLUMN username_login TINYINT(1) NOT NULL DEFAULT 0",
        "ALTER TABLE tb_user ADD COLUMN is_anonymous TINYINT(1) NOT NULL DEFAULT 0",
        "CREATE UNIQUE INDEX uk_tb_user_username ON tb_user (username)",
    )
    with engine.begin() as conn:
        for ddl in statements:
            try:
                conn.execute(text(ddl))
            except Exception as exc:
                msg = str(exc).lower()
                if "duplicate column" in msg or "1060" in msg:
                    continue
                if "duplicate key" in msg or "1061" in msg:
                    continue
                raise
    try:
        columns = {col["name"] for col in inspect(engine).get_columns("tb_user")}
    except Exception:
        return
    if {"username", "username_login", "is_anonymous"} <= columns:
        _columns_ready = True


def find_user_by_username(db, username, exclude_user_id=None):
    value = (username or "").strip()
    if not value:
        return None
    query = db.query(User).filter(func.lower(User.username) == value.lower())
    if exclude_user_id is not None:
        query = query.filter(User.user_id != int(exclude_user_id))
    return query.first()


def account_conflict(db, username, exclude_user_id=None):
    """用户名不能占用别人的手机号或邮箱，否则登录时会对不上人。"""
    value = (username or "").strip()
    if not value:
        return None
    query = db.query(User).filter(or_(User.telephone == value, User.email == value))
    if exclude_user_id is not None:
        query = query.filter(User.user_id != int(exclude_user_id))
    return query.first()
