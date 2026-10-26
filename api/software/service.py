import datetime
import json
import os
import re
import uuid

from pathlib import Path
from urllib.parse import quote, unquote

from sqlalchemy import case, inspect, or_, text

from api.admin.auth import require_admin, resolve_login_user, is_admin_user
from api.software.schemas import (
    CategoryCreate,
    CategoryListQuery,
    CategoryUpdate,
    ReviewAction,
    ReviewListQuery,
    SoftwareCreate,
    SoftwareListQuery,
    SoftwareUpdate,
    UserSoftwareSubmit,
)
from api.users.models import Software, SoftwareCategory
from app.http import json_response
from settings.database import engine
from settings.dependencies import REDIS_TOOL
from settings.macro import FILE_STORE_LINUX_PWD
from utils.res_code import Code, ERROR_MAP

MIN_NAME = 1
MAX_CATEGORY_NAME = 50
MAX_SOFTWARE_NAME = 200
MAX_SUMMARY = 5000
MAX_HTTP_COVER = 500
MAX_DATA_COVER = 400 * 1024
MAX_VERSION = 50
MAX_LINKS = 10
MAX_LINK_LABEL = 30
MAX_LINK_URL = 500
MAX_LINK_CODE = 50
MAX_KEYWORD = 100
MAX_CHANGELOG = 2000
MAX_REPO_URL = 500
MAX_REVIEW_NOTE = 500
MAX_PLATFORMS = 3
MAX_DAILY_SUBMISSIONS = 5
MAX_PENDING_SUBMISSIONS = 10

# 用户上传配额（契约 3.8 要求「如实现必须有配额」）：
# 单用户每天 5 次、累计 500MB，计数放 Redis，24 小时自然过期。
MAX_USER_UPLOADS_PER_DAY = 5
MAX_USER_UPLOAD_BYTES = 500 * 1024 * 1024
UPLOAD_QUOTA_TTL = 24 * 60 * 60

PLATFORMS = ("windows", "macos", "linux")
SOURCE_VALUES = ("official", "user")
OFFICIAL_AUTHOR = "anyGPT 官方"
REVIEW_STATUSES = ("pending", "approved", "rejected")

# 安装包与封面白名单。只按扩展名判断，不做内容嗅探——上传目录不在 Web 根下，
# 下载时强制 attachment，不让浏览器按 html/svg 解析。
PACKAGE_EXTS = (
    ".exe", ".msi", ".dmg", ".pkg", ".zip", ".7z", ".rar", ".tar", ".gz",
    ".appimage", ".deb", ".rpm",
)
COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MAX_PACKAGE_SIZE = 200 * 1024 * 1024
MAX_COVER_SIZE = 5 * 1024 * 1024
UPLOAD_SUBDIR = "software"
DOWNLOAD_PREFIX = os.environ.get("SOFTWARE_DOWNLOAD_PREFIX", "/apiAI/user/software/download")


_SCHEMA_READY = False


def ensure_software_tables():
    """建表 + 补列。每个进程只真正执行一次，避免每个请求都反射表结构。"""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    SoftwareCategory.__table__.create(bind=engine, checkfirst=True)
    Software.__table__.create(bind=engine, checkfirst=True)
    _ensure_cover_mediumtext()
    _ensure_software_columns()
    _SCHEMA_READY = True


# 新增列的定义：老库升级时逐列补，已存在就跳过。
# 用原生 DDL 而不是 alembic，和本项目其它 ensure_* 的做法保持一致。
_SOFTWARE_NEW_COLUMNS = (
    ("platforms", "JSON NULL"),
    ("changelog", "TEXT NULL"),
    ("repo_url", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ("source", "VARCHAR(16) NOT NULL DEFAULT 'official'"),
    ("review_status", "VARCHAR(16) NOT NULL DEFAULT 'approved'"),
    ("author_user_id", "INT NULL"),
    ("author_name", "VARCHAR(100) NOT NULL DEFAULT ''"),
    ("reviewer_user_id", "INT NULL"),
    ("reviewer_name", "VARCHAR(100) NOT NULL DEFAULT ''"),
    ("reviewer_note", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ("reviewed_at", "DATETIME NULL"),
    ("download_count", "INT NOT NULL DEFAULT 0"),
)


def _ensure_software_columns():
    """给已有的 tb_software 补多平台/审核相关列，并把存量记录回填成官方。

    存量 4 条都是站长在后台手录的，按契约一律 source=official、review_status=approved，
    否则商城「官方软件」页签会一直是空的。
    """
    try:
        columns = {col["name"] for col in inspect(engine).get_columns("tb_software")}
    except Exception:
        return
    with engine.begin() as conn:
        for name, ddl in _SOFTWARE_NEW_COLUMNS:
            if name not in columns:
                conn.execute(text("ALTER TABLE tb_software ADD COLUMN %s %s" % (name, ddl)))
        # 老数据的 source / review_status 可能是空串或 NULL，按「站长手录 = 官方已审」回填
        conn.execute(text(
            "UPDATE tb_software SET source='official' WHERE source IS NULL OR source=''"
        ))
        conn.execute(text(
            "UPDATE tb_software SET review_status='approved' "
            "WHERE review_status IS NULL OR review_status=''"
        ))


def _ensure_cover_mediumtext():
    """已有表的 cover_url 是 VARCHAR(500)，放不下压缩后的图片。"""
    try:
        columns = inspect(engine).get_columns("tb_software")
    except Exception:
        return
    cover = next((col for col in columns if col["name"] == "cover_url"), None)
    if not cover:
        return
    type_name = str(cover.get("type") or "").lower()
    if "mediumtext" in type_name or "longtext" in type_name:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tb_software MODIFY COLUMN cover_url MEDIUMTEXT NULL"))


def _fmt_time(value):
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or ""


def _like_pattern(value):
    escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_").replace("\\", "!\\")
    return "%" + escaped + "%"


def _is_http_url(value):
    lowered = (value or "").strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _is_internal_url(value):
    """站内上传落盘后的地址形如 ``/apiAI/user/software/download/<uuid>.exe``。

    这类地址不是 http(s)，但它是我们自己刚上传的文件，必须允许回填到
    platforms/cover，否则「上传安装包 → 提交」这条路会被校验挡死。
    """
    lowered = (value or "").strip()
    return lowered.startswith(DOWNLOAD_PREFIX.rstrip("/") + "/")


_DATA_IMAGE = re.compile(
    r"^data:image/(?:jpeg|jpg|png|webp|gif);base64,[A-Za-z0-9+/]+={0,2}$",
    re.IGNORECASE,
)


def _valid_cover(value):
    if not value:
        return True
    if _is_http_url(value) or _is_internal_url(value):
        return len(value) <= MAX_HTTP_COVER
    return len(value) <= MAX_DATA_COVER and bool(_DATA_IMAGE.match(value))


def _as_dict(item):
    """pydantic v2 用 model_dump，v1 用 dict；普通 dict 原样返回。"""
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return item


def _to_int(value, default=0):
    """老数据的 file_size 可能是 "12.4 MB" 这种字符串，转不动就退回默认值。"""
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_links(links):
    cleaned = []
    for item in links or []:
        data = _as_dict(item)
        if not isinstance(data, dict):
            continue
        label = str(data.get("label") or "").strip()
        url = str(data.get("url") or "").strip()
        code = str(data.get("code") or "").strip()
        if label or url or code:
            cleaned.append({"label": label, "url": url, "code": code})
    return cleaned


def _validate_links(links):
    if not links:
        return "请至少填写一条下载链接"
    if len(links) > MAX_LINKS:
        return "下载链接最多 %s 条" % MAX_LINKS
    for index, item in enumerate(links, start=1):
        label = item.get("label") or ""
        url = item.get("url") or ""
        code = item.get("code") or ""
        if not (1 <= len(label) <= MAX_LINK_LABEL):
            return "第 %s 条链接名称请控制在 1-%s 字" % (index, MAX_LINK_LABEL)
        if not (1 <= len(url) <= MAX_LINK_URL) or not (_is_http_url(url) or _is_internal_url(url)):
            return "第 %s 条链接需要以 http:// 或 https:// 开头" % index
        if len(code) > MAX_LINK_CODE:
            return "第 %s 条提取码请控制在 %s 字以内" % (index, MAX_LINK_CODE)
    return ""


def _invalid(message):
    return _fail(Code.FEEDBACK_INVALID, message)


def _fail(code, message):
    """错误响应。

    必须带 ``data`` 和 ``message`` 两个键：前端拦截器只把「code + data + message
    三件套」当成标准响应，缺一个就会重包成 ``{code: HTTP状态}``，业务错误码被抹平，
    提交失败也会被当成成功。``data.code`` 是给错误弹窗取 codeMsg 用的。
    """
    code_value = int(code)
    return json_response({
        "code": code_value,
        "codeMsg": message,
        "message": message,
        "data": {"code": code_value, "codeMsg": message},
    })


def _ok(data=None, message=None, **extra):
    """成功响应：code 用数字 0，业务数据放在 data 里，顶层再冗余一份给老前端。

    ``data`` 里也补一份 ``code``/``codeMsg``：老后台页读的是 ``res.data.code === '0'``
    和 ``res.data.codeMsg``，缺了就会显示兜底文案。
    """
    payload = dict(data) if data else {}
    payload.setdefault("code", str(Code.OK))
    payload.setdefault("codeMsg", message or ERROR_MAP[Code.OK])
    body = {
        "code": int(Code.OK),
        "codeMsg": message or ERROR_MAP[Code.OK],
        "message": message or "ok",
        "data": payload,
    }
    body.update(extra)
    return json_response(body)


def _ok_list(items, total, page=None, page_num=None, message=None, **extra):
    """列表响应：``data`` 里给一份完整分页，顶层再冗余一份（老页面只读顶层）。"""
    data = {"list": items, "total": total}
    if page is not None:
        data["page"] = page
    if page_num is not None:
        data["page_num"] = page_num
    data.update(extra)
    top = dict(data)
    return _ok(data=data, message=message, **top)


def _category_item(row):
    return {
        "id": row.id,
        "name": row.name or "",
        "sort": int(row.sort or 0),
        "status": int(row.status or 0),
        "insert_time": _fmt_time(row.insert_time),
        "update_time": _fmt_time(row.update_time),
        "is_delete": bool(row.is_delete),
    }


def _read_links(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    return _normalize_links(value)


def _read_platforms(row):
    """读出多平台数组；老记录没有该列值时用 links 里的平台名兜底。

    商城卡片、详情页、后台审核都要按平台渲染，所以这里统一产出
    ``[{platform, file_url, file_size, version, download_count}]``。
    """
    raw = getattr(row, "platforms", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = None
    cleaned = []
    seen = set()
    for item in raw or []:
        data = _as_dict(item)
        if not isinstance(data, dict):
            continue
        platform = str(data.get("platform") or "").strip().lower()
        url = str(data.get("file_url") or "").strip()
        if platform not in PLATFORMS or platform in seen or not url:
            continue
        seen.add(platform)
        cleaned.append({
            "platform": platform,
            "file_url": url,
            "file_size": _to_int(data.get("file_size")),
            "version": str(data.get("version") or "").strip(),
            "download_count": _to_int(data.get("download_count")),
        })
    if cleaned:
        return cleaned
    # 老数据只有 links，label 里常写平台名（Windows / macOS / Linux）
    for link in _read_links(getattr(row, "links", None)):
        url = link.get("url") or ""
        platform = _platform_from_label(link.get("label"))
        if not platform or not url or platform in seen:
            continue
        seen.add(platform)
        cleaned.append({
            "platform": platform,
            "file_url": url,
            "file_size": 0,
            "version": "",
            "download_count": 0,
        })
    return cleaned


def _software_item(row, category_name="", include_author=False):
    source = getattr(row, "source", "") or "official"
    platforms = _read_platforms(row)
    primary = platforms[0] if platforms else {}
    # 官方条目对外统一显示 OFFICIAL_AUTHOR（契约 3.4：官方填「anyGPT 官方」）
    author_name = OFFICIAL_AUTHOR if source == "official" else (getattr(row, "author_name", "") or "")
    item = {
        "id": row.id,
        "category_id": int(row.category_id or 0),
        "category_name": category_name or "",
        "name": row.name or "",
        "summary": row.summary or "",
        "cover_url": row.cover_url or "",
        "version": row.version or "",
        "links": _read_links(row.links),
        "platforms": platforms,
        # 单数字段是 v2 起的「主平台摘要」，老前端/老后台只认它
        "platform": primary.get("platform", ""),
        "file_url": primary.get("file_url", ""),
        "file_size": primary.get("file_size", 0),
        "changelog": getattr(row, "changelog", "") or "",
        "repo_url": getattr(row, "repo_url", "") or "",
        "source": source,
        "author_name": author_name,
        "review_status": getattr(row, "review_status", "") or "approved",
        "reviewer_note": getattr(row, "reviewer_note", "") or "",
        "reviewed_at": _fmt_time(getattr(row, "reviewed_at", None)),
        "download_count": int(getattr(row, "download_count", 0) or 0),
        "sort": int(row.sort or 0),
        "status": int(row.status or 0),
        "insert_time": _fmt_time(row.insert_time),
        "update_time": _fmt_time(row.update_time),
        "is_delete": bool(row.is_delete),
    }
    if include_author:
        item["author_user_id"] = getattr(row, "author_user_id", None)
        item["reviewer_name"] = getattr(row, "reviewer_name", "") or None
    return item


def _normalize_platforms(platforms, default_version="", single=None):
    """把 platforms 数组和兼容期单数写法统一成 [{"platform","file_url","file_size","version"}]。

    返回 (cleaned, error)。规则与 v3 契约一致：
    同一平台不可重复、最多 3 个、三条相同链接是合法的。
    """
    if platforms:
        items = platforms
    elif single and (single.get("platform") or single.get("file_url")):
        items = [single]
    else:
        return [], "请至少选择一个平台"
    cleaned = []
    seen = set()
    for index, item in enumerate(items, start=1):
        data = _as_dict(item)
        if not isinstance(data, dict):
            continue
        platform = str(data.get("platform") or "").strip().lower()
        url = str(data.get("file_url") or "").strip()
        if platform not in PLATFORMS:
            return [], "平台只能是 windows、macos、linux"
        if platform in seen:
            return [], "平台不能重复选择"
        if not url:
            return [], "第 %s 个平台缺少下载链接" % index
        if len(url) > MAX_LINK_URL or not (_is_http_url(url) or _is_internal_url(url)):
            return [], "第 %s 个平台的下载地址需要以 http:// 或 https:// 开头" % index
        seen.add(platform)
        size = data.get("file_size")
        try:
            size_value = int(float(size)) if size not in (None, "") else 0
        except (TypeError, ValueError):
            size_value = 0
        cleaned.append({
            "platform": platform,
            "file_url": url,
            "file_size": size_value,
            "version": str(data.get("version") or "").strip() or default_version,
        })
    if not cleaned:
        return [], "请至少选择一个平台"
    if len(cleaned) > MAX_PLATFORMS:
        return [], "最多只能选 %s 个平台" % MAX_PLATFORMS
    return cleaned, ""


def _links_from_platforms(platforms):
    """平台数组同步写一份 links，保证老页面/老接口仍能显示下载入口。"""
    labels = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
    return [{"label": labels.get(item["platform"], item["platform"]),
             "url": item["file_url"], "code": ""} for item in platforms]


def _platform_from_label(label):
    """把 links[].label 归一成平台枚举；认不出返回 None（视为网盘等普通渠道）。"""
    text = (label or "").lower()
    if not text:
        return None
    if any(word in text for word in ("win", "exe", "微软")):
        return "windows"
    if any(word in text for word in ("mac", "osx", "dmg", "苹果", "darwin")):
        return "macos"
    if any(word in text for word in ("linux", "deb", "rpm", "appimage", "ubuntu")):
        return "linux"
    return None


def _merge_links_with_platforms(existing_links, platforms):
    """平台链接更新时，保留原有的网盘/官网等非平台链接。

    只按平台名重新生成 links 会把「百度网盘」这类渠道静默抹掉，
    所以这里以老 links 为底，只替换能识别成平台的条目。
    """
    kept = [link for link in _read_links(existing_links)
            if not _platform_from_label(link.get("label"))]
    return kept + _links_from_platforms(platforms)


def _merge_platforms(existing, incoming):
    """update 时按平台增量合并：传了哪几个就只改那几个，没传的保持原样。

    existing 可能是 JSON 列给出的 list，也可能是历史遗留的 JSON 字符串，先统一解析。
    """
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except (TypeError, ValueError):
            existing = []
    current = []
    for item in existing or []:
        if isinstance(item, dict) and item.get("platform"):
            current.append(dict(item))
    index = {item["platform"]: pos for pos, item in enumerate(current)}
    for item in incoming:
        entry = dict(item)
        pos = index.get(entry["platform"])
        if pos is None:
            current.append(entry)
            index[entry["platform"]] = len(current) - 1
        else:
            # 保留历史下载计数，只覆盖本次提交的字段
            entry["download_count"] = current[pos].get("download_count", 0)
            current[pos] = entry
    return current


def _submission_limit_error(db, user):
    """投稿限流：单日 5 次、未审记录不超过 10 条。"""
    since = datetime.datetime.now() - datetime.timedelta(days=1)
    daily = db.query(Software).filter(
        Software.author_user_id == user.user_id,
        Software.source == "user",
        Software.insert_time >= since,
    ).count()
    if daily >= MAX_DAILY_SUBMISSIONS:
        return "今天提交的次数已达上限，请明天再试"
    pending = db.query(Software).filter(
        Software.author_user_id == user.user_id,
        Software.source == "user",
        Software.review_status == "pending",
    ).count()
    if pending >= MAX_PENDING_SUBMISSIONS:
        return "待审核的投稿太多了，请等站长处理后再提交"
    return ""


def _safe_file_name(original, ext):
    """原始文件名清洗：去掉路径与非法字符，长度收敛，保留扩展名。

    只用于「落盘名」和下载时的展示名，安全边界仍是 uuid 前缀 + 目录不对外暴露。
    """
    name = os.path.basename(original or "")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip().strip(".")
    if not name:
        return ""
    stem = Path(name).stem[:80] or "package"
    return stem + ext


def save_upload(upload, kind):
    """把上传文件落盘，返回 (url, file_name, file_size) 或 (None, 错误信息, 0)。

    文件名一律重写为 uuid + 白名单扩展名，杜绝 ../ 与同名覆盖；
    下载走 attachment，避免被当成 html/svg 在站内执行。
    边读边写并计数，超过上限立刻中断——否则一个 200MB 的包会整块留在内存里。
    """
    original = os.path.basename(getattr(upload, "filename", "") or "")
    ext = Path(original).suffix.lower()
    is_cover = kind == "cover"
    allowed = COVER_EXTS if is_cover else PACKAGE_EXTS
    limit = MAX_COVER_SIZE if is_cover else MAX_PACKAGE_SIZE
    if ext not in allowed:
        return None, "只支持 %s 格式" % "、".join(item.lstrip(".") for item in allowed), 0
    folder = Path(FILE_STORE_LINUX_PWD) / UPLOAD_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    # uuid 前缀保证唯一，后面接清洗过的原始名，下载时还原给用户
    safe_name = _safe_file_name(original, ext)
    stored_name = "%s__%s" % (uuid.uuid4().hex, safe_name) if safe_name else "%s%s" % (uuid.uuid4().hex, ext)
    target = folder / stored_name
    size = 0
    too_large = "%s不能超过 %sMB" % ("封面" if is_cover else "安装包", limit // (1024 * 1024))
    try:
        with open(target, "wb") as handler:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    handler.close()
                    target.unlink(missing_ok=True)
                    return None, too_large, 0
                handler.write(chunk)
    except OSError:
        target.unlink(missing_ok=True)
        return None, "文件保存失败，请稍后重试", 0
    if size <= 0:
        target.unlink(missing_ok=True)
        return None, "文件是空的，请重新选择", 0
    # 落盘名可能含中文和空格，URL 里必须转义；FastAPI 收到的是解码后的路径参数
    return "%s/%s" % (DOWNLOAD_PREFIX.rstrip("/"), quote(stored_name, safe="")), original, size


def resolve_download(name):
    """把下载文件名还原成磁盘路径，拒绝任何带路径分隔符的输入。

    允许的形态只有两种：``<uuid>.<ext>`` 和 ``<uuid>__<原始名>.<ext>``；
    只要 basename 与入参不一致、含 ``..``、或解析后不在上传目录，一律拒绝。
    """
    plain = os.path.basename(name or "")
    if not plain or plain != name or ".." in plain or plain.startswith("."):
        return None
    if not re.match(r"^[0-9a-f]{32}(__[^/\\]+)?\.[A-Za-z0-9]+$", plain, re.IGNORECASE):
        return None
    folder = (Path(FILE_STORE_LINUX_PWD) / UPLOAD_SUBDIR).resolve()
    target = folder / plain
    try:
        if not target.is_file() or target.parent.resolve() != folder:
            return None
    except OSError:
        return None
    return target


def download_display_name(stored_name):
    """给用户看的下载文件名：去掉 uuid 前缀，保留原始名。"""
    plain = os.path.basename(stored_name or "")
    if "__" in plain:
        return plain.split("__", 1)[1]
    return plain


def bump_download_count(db, stored_name):
    """站内直链下载后累加计数：平台一次、软件合计一次。

    上传目录里的文件不带队名，只能反查哪条软件的 platforms 引用了它。
    软件量级很小（几十条），直接遍历即可；失败不影响下载本身。
    """
    suffix = "/" + stored_name
    try:
        rows = db.query(Software).filter(Software.is_delete == False).all()
    except Exception:
        return
    for row in rows:
        platforms = _read_platforms(row)
        # file_url 里存的是转义后的地址（中文名会变成 %E6..），比较前先还原
        hit = next(
            (item for item in platforms
             if unquote(str(item.get("file_url") or "")).endswith(suffix)),
            None,
        )
        if not hit:
            continue
        hit["download_count"] = int(hit.get("download_count") or 0) + 1
        try:
            db.query(Software).filter(Software.id == row.id).update({
                "platforms": platforms,
                "download_count": int(getattr(row, "download_count", 0) or 0) + 1,
            })
            db.commit()
        except Exception:
            db.rollback()
        return


def _category_names(db, category_ids):
    ids = [item for item in set(category_ids) if item]
    if not ids:
        return {}
    rows = db.query(SoftwareCategory).filter(SoftwareCategory.id.in_(ids)).all()
    return {row.id: row.name or "" for row in rows}


def _online_category(db, category_id):
    return db.query(SoftwareCategory).filter(
        SoftwareCategory.id == category_id,
        SoftwareCategory.is_delete == False,
    ).first()


class SoftwareService:
    def list_categories_public(self, common):
        ensure_software_tables()
        rows = (
            common.db.query(SoftwareCategory)
            .filter(SoftwareCategory.is_delete == False, SoftwareCategory.status == 1)
            .order_by(SoftwareCategory.sort.desc(), SoftwareCategory.id.desc())
            .all()
        )
        items = [_category_item(row) for row in rows]
        return _ok(data={"list": items}, list=items)

    def list_public(self, request_body: SoftwareListQuery, common):
        ensure_software_tables()
        page = request_body.page or 1
        page_num = request_body.page_num or 12
        keyword = (request_body.keyword or "").strip()
        if len(keyword) > MAX_KEYWORD:
            return _invalid("搜索关键字请控制在 %s 字以内" % MAX_KEYWORD)

        source = (request_body.source or "").strip().lower()
        if source and source not in SOURCE_VALUES:
            return _invalid("source 只能是 official 或 user")

        online_ids = common.db.query(SoftwareCategory.id).filter(
            SoftwareCategory.is_delete == False,
            SoftwareCategory.status == 1,
        )
        query = common.db.query(Software).filter(
            Software.is_delete == False,
            Software.status == 1,
            Software.review_status == "approved",
            Software.category_id.in_(online_ids),
        )
        if source:
            query = query.filter(Software.source == source)
        if request_body.category_id:
            query = query.filter(Software.category_id == request_body.category_id)
        if keyword:
            pattern = _like_pattern(keyword)
            query = query.filter(or_(
                Software.name.ilike(pattern, escape="!"),
                Software.summary.ilike(pattern, escape="!"),
            ))
        total = query.count()
        rows = (
            # 契约建议官方置顶，再按 sort / id 排
            query.order_by(
                case((Software.source == "official", 0), else_=1),
                Software.sort.desc(),
                Software.id.desc(),
            )
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        names = _category_names(common.db, [row.category_id for row in rows])
        items = [_software_item(row, names.get(row.category_id, "")) for row in rows]
        return _ok_list(items, total, page=page, page_num=page_num, keyword=keyword)

    def detail(self, software_id, common):
        """详情。已上架的对游客开放；待审/已驳回的只允许作者本人和管理员查看。"""
        ensure_software_tables()
        row = common.db.query(Software).filter(
            Software.id == software_id,
            Software.is_delete == False,
        ).first()
        if not row:
            return _fail(Code.PROJECT_INVALID, "软件不存在")
        if not (row.status == 1 and row.review_status == "approved"):
            user = resolve_login_user(common)
            if not user or (user.user_id != row.author_user_id and not is_admin_user(user)):
                return _fail(Code.PROJECT_INVALID, "软件不存在或已下架")
        names = _category_names(common.db, [row.category_id])
        item = _software_item(row, names.get(row.category_id, ""), include_author=True)
        # 前端详情页读 data.item || data；放在 item 里可以避免 code/codeMsg 混进记录本身
        return _ok(data={"item": item}, item=item)

    def list_categories_admin(self, request_body: CategoryListQuery, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        page = request_body.page or 1
        page_num = request_body.page_num or 10
        query = common.db.query(SoftwareCategory).filter(SoftwareCategory.is_delete == False)
        total = query.count()
        rows = (
            query.order_by(SoftwareCategory.sort.desc(), SoftwareCategory.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        items = [_category_item(row) for row in rows]
        return _ok_list(items, total, page=page, page_num=page_num)

    def create_category(self, request_body: CategoryCreate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        name = (request_body.name or "").strip()
        if not (MIN_NAME <= len(name) <= MAX_CATEGORY_NAME):
            return _invalid("分类名称请控制在 %s-%s 字" % (MIN_NAME, MAX_CATEGORY_NAME))
        now = datetime.datetime.now()
        item = SoftwareCategory(
            name=name,
            status=1 if int(request_body.status or 0) == 1 else 0,
            sort=int(request_body.sort or 0),
            insert_time=now,
            update_time=now,
        )
        common.db.add(item)
        common.db.commit()
        common.db.refresh(item)
        category = _category_item(item)
        return _ok(data={"item": category}, message="分类已创建", item=category)

    def update_category(self, request_body: CategoryUpdate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        row = common.db.query(SoftwareCategory).filter(SoftwareCategory.id == request_body.id).first()
        if not row or row.is_delete:
            return _invalid("分类不存在")
        if request_body.is_delete:
            using = common.db.query(Software).filter(
                Software.category_id == row.id,
                Software.is_delete == False,
            ).count()
            if using:
                return _invalid("该分类下还有软件，请先移动或删除")
        payload = {"update_time": datetime.datetime.now()}
        if request_body.name is not None:
            name = request_body.name.strip()
            if not (MIN_NAME <= len(name) <= MAX_CATEGORY_NAME):
                return _invalid("分类名称请控制在 %s-%s 字" % (MIN_NAME, MAX_CATEGORY_NAME))
            payload["name"] = name
        if request_body.status is not None:
            payload["status"] = 1 if int(request_body.status) == 1 else 0
        if request_body.sort is not None:
            payload["sort"] = int(request_body.sort)
        if request_body.is_delete is not None:
            payload["is_delete"] = bool(request_body.is_delete)
        common.db.query(SoftwareCategory).filter(SoftwareCategory.id == request_body.id).update(payload)
        common.db.commit()
        row = common.db.query(SoftwareCategory).filter(SoftwareCategory.id == request_body.id).first()
        category = _category_item(row) if row else None
        return _ok(data={"item": category}, message="更新成功", item=category)

    def list_admin(self, request_body: SoftwareListQuery, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        page = request_body.page or 1
        page_num = request_body.page_num or 10
        query = common.db.query(Software).filter(Software.is_delete == False)
        if request_body.category_id:
            query = query.filter(Software.category_id == request_body.category_id)
        keyword = (request_body.keyword or "").strip()
        if keyword:
            if len(keyword) > MAX_KEYWORD:
                return _invalid("搜索关键字请控制在 %s 字以内" % MAX_KEYWORD)
            pattern = _like_pattern(keyword)
            query = query.filter(or_(
                Software.name.ilike(pattern, escape="!"),
                Software.summary.ilike(pattern, escape="!"),
            ))
        total = query.count()
        rows = (
            query.order_by(Software.sort.desc(), Software.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        names = _category_names(common.db, [row.category_id for row in rows])
        items = [
            _software_item(row, names.get(row.category_id, ""), include_author=True)
            for row in rows
        ]
        return _ok_list(items, total, page=page, page_num=page_num)

    def create(self, request_body: SoftwareCreate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        category = _online_category(common.db, request_body.category_id)
        if not category:
            return _invalid("请选择有效分类")
        name = (request_body.name or "").strip()
        summary = (request_body.summary or "").strip()
        cover_url = (request_body.cover_url or "").strip()
        version = (request_body.version or "").strip()
        if not (MIN_NAME <= len(name) <= MAX_SOFTWARE_NAME):
            return _invalid("软件名称请控制在 %s-%s 字" % (MIN_NAME, MAX_SOFTWARE_NAME))
        if len(summary) > MAX_SUMMARY:
            return _invalid("简介请控制在 %s 字以内" % MAX_SUMMARY)
        if not _valid_cover(cover_url):
            return _invalid("封面请上传图片，或填写 http:// / https:// 地址")
        if len(version) > MAX_VERSION:
            return _invalid("版本号请控制在 %s 字以内" % MAX_VERSION)
        links = _normalize_links(request_body.links)
        platform_error = ""
        if request_body.platforms or request_body.platform or request_body.file_url:
            platforms, platform_error = _normalize_platforms(
                request_body.platforms,
                version,
                {"platform": request_body.platform,
                 "file_url": request_body.file_url,
                 "file_size": request_body.file_size},
            )
            if platform_error:
                return _invalid(platform_error)
            # 管理员可能同时给了网盘链接：平台链接替换同名条目，其它保留
            links = _merge_links_with_platforms(links, platforms)
        else:
            platforms = []
        # platforms 生成的链接一定合法，但管理员可能另外带了网盘链接，一并校验
        link_error = _validate_links(links) if links else "请至少填写一条下载链接"
        if link_error:
            return _invalid(link_error)
        if len((request_body.changelog or "").strip()) > MAX_CHANGELOG:
            return _invalid("更新说明请控制在 %s 字以内" % MAX_CHANGELOG)
        if len((request_body.repo_url or "").strip()) > MAX_REPO_URL:
            return _invalid("仓库地址过长")
        now = datetime.datetime.now()
        item = Software(
            category_id=category.id,
            name=name,
            summary=summary,
            cover_url=cover_url,
            version=version,
            links=links,
            platforms=platforms,
            changelog=(request_body.changelog or "").strip(),
            repo_url=(request_body.repo_url or "").strip(),
            # 来源与审核结论由服务端强制，管理员创建即官方上架
            source="official",
            review_status="approved",
            # 对外展示统一是「anyGPT 官方」；具体是谁上传的记在 reviewer_* 里
            author_user_id=admin.user_id,
            author_name=OFFICIAL_AUTHOR,
            reviewer_user_id=admin.user_id,
            reviewer_name=admin.name or admin.username or "",
            reviewed_at=now,
            download_count=0,
            status=1 if int(request_body.status or 0) == 1 else 0,
            sort=int(request_body.sort or 0),
            insert_time=now,
            update_time=now,
        )
        common.db.add(item)
        common.db.commit()
        common.db.refresh(item)
        created = _software_item(item, category.name or "", include_author=True)
        return _ok(data={"id": item.id, "item": created}, message="软件已创建",
                   id=item.id, item=created)

    def update(self, request_body: SoftwareUpdate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        row = common.db.query(Software).filter(Software.id == request_body.id).first()
        if not row or row.is_delete:
            return _invalid("软件不存在")
        payload = {"update_time": datetime.datetime.now()}
        category_name = ""
        if request_body.category_id is not None:
            category = _online_category(common.db, request_body.category_id)
            if not category:
                return _invalid("请选择有效分类")
            payload["category_id"] = category.id
            category_name = category.name or ""
        if request_body.name is not None:
            name = request_body.name.strip()
            if not (MIN_NAME <= len(name) <= MAX_SOFTWARE_NAME):
                return _invalid("软件名称请控制在 %s-%s 字" % (MIN_NAME, MAX_SOFTWARE_NAME))
            payload["name"] = name
        if request_body.summary is not None:
            summary = request_body.summary.strip()
            if len(summary) > MAX_SUMMARY:
                return _invalid("简介请控制在 %s 字以内" % MAX_SUMMARY)
            payload["summary"] = summary
        if request_body.cover_url is not None:
            cover_url = request_body.cover_url.strip()
            if not _valid_cover(cover_url):
                return _invalid("封面请上传图片，或填写 http:// / https:// 地址")
            payload["cover_url"] = cover_url
        if request_body.version is not None:
            version = request_body.version.strip()
            if len(version) > MAX_VERSION:
                return _invalid("版本号请控制在 %s 字以内" % MAX_VERSION)
            payload["version"] = version
        if request_body.links is not None:
            links = _normalize_links(request_body.links)
            link_error = _validate_links(links)
            if link_error:
                return _invalid(link_error)
            payload["links"] = links
        # platforms 增量更新：只改传了的平台，没传的保持原样（契约 v3 推荐语义）
        if request_body.platforms is not None or request_body.platform is not None:
            incoming, platform_error = _normalize_platforms(
                request_body.platforms or [],
                request_body.version if request_body.version is not None else (row.version or ""),
                {"platform": request_body.platform,
                 "file_url": request_body.file_url,
                 "file_size": request_body.file_size},
            )
            if platform_error:
                return _invalid(platform_error)
            merged = _merge_platforms(row.platforms, incoming)
            payload["platforms"] = merged
            # 本次也传了 links 就以本次为准（保留其中非平台的网盘条目）
            base_links = request_body.links if request_body.links is not None else row.links
            payload["links"] = _merge_links_with_platforms(base_links, merged)
        if request_body.changelog is not None:
            changelog = request_body.changelog.strip()
            if len(changelog) > MAX_CHANGELOG:
                return _invalid("更新说明请控制在 %s 字以内" % MAX_CHANGELOG)
            payload["changelog"] = changelog
        if request_body.repo_url is not None:
            repo_url = request_body.repo_url.strip()
            if len(repo_url) > MAX_REPO_URL:
                return _invalid("仓库地址过长")
            payload["repo_url"] = repo_url
        if request_body.status is not None:
            payload["status"] = 1 if int(request_body.status) == 1 else 0
        if request_body.sort is not None:
            payload["sort"] = int(request_body.sort)
        if request_body.is_delete is not None:
            payload["is_delete"] = bool(request_body.is_delete)
        common.db.query(Software).filter(Software.id == request_body.id).update(payload)
        common.db.commit()
        row = common.db.query(Software).filter(Software.id == request_body.id).first()
        if row and not category_name:
            names = _category_names(common.db, [row.category_id])
            category_name = names.get(row.category_id, "")
        updated = _software_item(row, category_name, include_author=True) if row else None
        return _ok(data={"id": request_body.id, "item": updated}, message="更新成功",
                   id=request_body.id, item=updated)

    def submit(self, request_body: UserSoftwareSubmit, common):
        """用户投稿：服务端强制 source=user、review_status=pending、status=0。

        分类允许留空（前端表单是选填），此时落在当前排序最前的上线分类里，
        否则前端分类筛选会因为 category_id=0 而永远看不到这条。
        """
        ensure_software_tables()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])

        name = (request_body.name or "").strip()
        summary = (request_body.summary or "").strip()
        version = (request_body.version or "").strip()
        changelog = (request_body.changelog or "").strip()
        repo_url = (request_body.repo_url or "").strip()
        if not (MIN_NAME <= len(name) <= MAX_SOFTWARE_NAME):
            return _invalid("软件名称请控制在 %s-%s 字" % (MIN_NAME, MAX_SOFTWARE_NAME))
        if not summary:
            return _invalid("请写一句简介，站长审核时要看")
        if len(summary) > MAX_SUMMARY:
            return _invalid("简介请控制在 %s 字以内" % MAX_SUMMARY)
        if not (MIN_NAME <= len(version) <= MAX_VERSION):
            return _invalid("版本号请控制在 %s-%s 字" % (MIN_NAME, MAX_VERSION))
        if len(changelog) > MAX_CHANGELOG:
            return _invalid("更新说明请控制在 %s 字以内" % MAX_CHANGELOG)
        if len(repo_url) > MAX_REPO_URL:
            return _invalid("仓库地址过长")

        # 不许和官方软件重名，防止用户冒充官方
        clash = common.db.query(Software).filter(
            Software.name == name,
            Software.source == "official",
            Software.is_delete == False,
        ).first()
        if clash:
            return _fail(Code.USER_EXIST, "该名称与官方软件重名，请换一个")

        category = None
        if request_body.category_id:
            category = _online_category(common.db, request_body.category_id)
            if not category:
                return _invalid("请选择有效分类")
        if not category:
            category = (
                common.db.query(SoftwareCategory)
                .filter(SoftwareCategory.is_delete == False, SoftwareCategory.status == 1)
                .order_by(SoftwareCategory.sort.desc(), SoftwareCategory.id.desc())
                .first()
            )
        if not category:
            return _invalid("商城还没有可用分类，请联系站长")

        platforms, platform_error = _normalize_platforms(request_body.platforms, version)
        if platform_error:
            return _invalid(platform_error)

        limit_error = _submission_limit_error(common.db, user)
        if limit_error:
            return _fail(Code.FEEDBACK_TOO_FAST, limit_error)

        now = datetime.datetime.now()
        item = Software(
            category_id=category.id,
            name=name,
            summary=summary,
            cover_url="",
            version=version,
            links=_links_from_platforms(platforms),
            platforms=platforms,
            changelog=changelog,
            repo_url=repo_url,
            source="user",
            review_status="pending",
            author_user_id=user.user_id,
            author_name=user.name or user.username or "",
            download_count=0,
            status=0,
            sort=0,
            insert_time=now,
            update_time=now,
        )
        common.db.add(item)
        common.db.commit()
        common.db.refresh(item)
        return _ok(
            data={"id": item.id, "review_status": "pending"},
            message="已提交，等待站长审核",
            id=item.id,
            review_status="pending",
        )

    def list_mine(self, common):
        ensure_software_tables()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])
        rows = (
            common.db.query(Software)
            .filter(
                Software.author_user_id == user.user_id,
                Software.source == "user",
                Software.is_delete == False,
            )
            .order_by(Software.update_time.desc(), Software.id.desc())
            .all()
        )
        names = _category_names(common.db, [row.category_id for row in rows])
        items = [
            _software_item(row, names.get(row.category_id, ""), include_author=True)
            for row in rows
        ]
        return _ok_list(items, len(items), page=1, page_num=len(items) or 1)

    def review_list(self, request_body: ReviewListQuery, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        # 前端「全部」页签是**不传 status**（只传 pending/approved/rejected），
        # 所以缺省按 all 处理；后台页默认页签自己会显式传 pending。
        status = (request_body.status or "all").strip().lower()
        query = common.db.query(Software).filter(
            Software.source == "user",
            Software.is_delete == False,
        )
        if status and status != "all":
            if status not in REVIEW_STATUSES:
                return _invalid("status 只能是 pending / approved / rejected / all")
            query = query.filter(Software.review_status == status)
        total = query.count()
        rows = (
            query.order_by(Software.update_time.desc(), Software.id.desc())
            .offset((request_body.page - 1) * request_body.page_num)
            .limit(request_body.page_num)
            .all()
        )
        names = _category_names(common.db, [row.category_id for row in rows])
        items = []
        for row in rows:
            item = _software_item(row, names.get(row.category_id, ""), include_author=True)
            item["platform_count"] = len(item["platforms"])
            items.append(item)
        return _ok_list(items, total, page=request_body.page, page_num=request_body.page_num)

    def review(self, request_body: ReviewAction, common):
        """整条审核：一次动作作用于该投稿的全部平台。"""
        admin, error = require_admin(common)
        if error:
            return error
        ensure_software_tables()
        action = (request_body.action or "").strip().lower()
        if action not in ("approve", "reject"):
            return _invalid("action 只能是 approve 或 reject")
        note = (request_body.note or "").strip()
        if action == "reject" and not note:
            return _invalid("驳回必须写原因，用户要知道怎么改")
        if len(note) > MAX_REVIEW_NOTE:
            return _invalid("审核备注请控制在 %s 字以内" % MAX_REVIEW_NOTE)

        row = common.db.query(Software).filter(
            Software.id == request_body.id,
            Software.source == "user",
            Software.is_delete == False,
        ).first()
        if not row:
            return _fail(Code.PROJECT_INVALID, "投稿不存在")
        if row.review_status != "pending":
            return _fail(Code.PROJECT_INVALID, "这条投稿已经处理过了，请刷新列表")

        now = datetime.datetime.now()
        reviewer = admin.name or admin.username or ""
        review_status = "approved" if action == "approve" else "rejected"
        payload = {
            "review_status": review_status,
            "status": 1 if action == "approve" else 0,
            "reviewer_user_id": admin.user_id,
            "reviewer_name": reviewer,
            "reviewer_note": note,
            "reviewed_at": now,
            "update_time": now,
        }
        common.db.query(Software).filter(Software.id == row.id).update(payload)
        common.db.commit()
        return _ok(data={"id": row.id, "review_status": review_status},
                   id=row.id, review_status=review_status)

    def upload_admin_file(self, upload, kind, common):
        admin, error = require_admin(common)
        if error:
            return error
        return _upload(upload, kind)

    def upload_user_file(self, upload, kind, common):
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])
        # 只对安装包计配额；封面是小图，走同一套限制反而不好用
        return _upload(upload, kind, user=user)


def _user_upload_quota_error(user):
    """用户上传配额：5 次/天、累计 500MB。Redis 不可用时放行，不阻断主流程。"""
    try:
        count_key = "software:upload:count:%s" % user.user_id
        size_key = "software:upload:size:%s" % user.user_id
        count = int(REDIS_TOOL.get(count_key) or 0)
        used = int(REDIS_TOOL.get(size_key) or 0)
    except Exception:
        return ""
    if count >= MAX_USER_UPLOADS_PER_DAY:
        return "今天的上传次数已达上限，请明天再试"
    if used >= MAX_USER_UPLOAD_BYTES:
        return "上传总量已超过 500MB，请改用网盘链接"
    return ""


def _bump_user_upload_quota(user, size):
    try:
        for key, delta in (
            ("software:upload:count:%s" % user.user_id, 1),
            ("software:upload:size:%s" % user.user_id, size),
        ):
            if delta == 1:
                REDIS_TOOL.incr(key, delta)
            else:
                REDIS_TOOL.incrby(key, delta)
            if REDIS_TOOL.ttl(key) < 0:
                REDIS_TOOL.expire(key, UPLOAD_QUOTA_TTL)
    except Exception:
        pass


def _upload(upload, kind, user=None):
    kind = (kind or "package").strip().lower()
    if kind not in ("package", "cover"):
        return _invalid("kind 只能是 package 或 cover")
    if user is not None and kind == "package":
        quota_error = _user_upload_quota_error(user)
        if quota_error:
            return _fail(Code.FEEDBACK_TOO_FAST, quota_error)
    url, name_or_error, file_size = save_upload(upload, kind)
    if not url:
        return _invalid(name_or_error)
    if user is not None and kind == "package":
        _bump_user_upload_quota(user, file_size)
    payload = {"url": url, "file_name": name_or_error, "file_size": file_size}
    return _ok(data=payload, **payload)


software_service = SoftwareService()
