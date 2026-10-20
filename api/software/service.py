import datetime
import json
import re

from sqlalchemy import inspect, or_, text

from api.admin.auth import require_admin
from api.software.schemas import (
    CategoryCreate,
    CategoryListQuery,
    CategoryUpdate,
    SoftwareCreate,
    SoftwareListQuery,
    SoftwareUpdate,
)
from api.users.models import Software, SoftwareCategory
from app.http import json_response
from settings.database import engine
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


def ensure_software_tables():
    SoftwareCategory.__table__.create(bind=engine, checkfirst=True)
    Software.__table__.create(bind=engine, checkfirst=True)
    _ensure_cover_mediumtext()


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


_DATA_IMAGE = re.compile(
    r"^data:image/(?:jpeg|jpg|png|webp|gif);base64,[A-Za-z0-9+/]+={0,2}$",
    re.IGNORECASE,
)


def _valid_cover(value):
    if not value:
        return True
    if _is_http_url(value):
        return len(value) <= MAX_HTTP_COVER
    return len(value) <= MAX_DATA_COVER and bool(_DATA_IMAGE.match(value))


def _normalize_links(links):
    cleaned = []
    for item in links or []:
        data = item.dict() if hasattr(item, "dict") else item
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
        if not (1 <= len(url) <= MAX_LINK_URL) or not _is_http_url(url):
            return "第 %s 条链接需要以 http:// 或 https:// 开头" % index
        if len(code) > MAX_LINK_CODE:
            return "第 %s 条提取码请控制在 %s 字以内" % (index, MAX_LINK_CODE)
    return ""


def _invalid(message):
    return json_response({
        "code": str(Code.FEEDBACK_INVALID),
        "codeMsg": message,
    })


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


def _software_item(row, category_name=""):
    return {
        "id": row.id,
        "category_id": int(row.category_id or 0),
        "category_name": category_name or "",
        "name": row.name or "",
        "summary": row.summary or "",
        "cover_url": row.cover_url or "",
        "version": row.version or "",
        "links": _read_links(row.links),
        "sort": int(row.sort or 0),
        "status": int(row.status or 0),
        "insert_time": _fmt_time(row.insert_time),
        "update_time": _fmt_time(row.update_time),
        "is_delete": bool(row.is_delete),
    }


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
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [_category_item(row) for row in rows],
        })

    def list_public(self, request_body: SoftwareListQuery, common):
        ensure_software_tables()
        page = request_body.page or 1
        page_num = request_body.page_num or 12
        keyword = (request_body.keyword or "").strip()
        if len(keyword) > MAX_KEYWORD:
            return _invalid("搜索关键字请控制在 %s 字以内" % MAX_KEYWORD)

        online_ids = common.db.query(SoftwareCategory.id).filter(
            SoftwareCategory.is_delete == False,
            SoftwareCategory.status == 1,
        )
        query = common.db.query(Software).filter(
            Software.is_delete == False,
            Software.status == 1,
            Software.category_id.in_(online_ids),
        )
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
            query.order_by(Software.sort.desc(), Software.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        names = _category_names(common.db, [row.category_id for row in rows])
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [_software_item(row, names.get(row.category_id, "")) for row in rows],
            "page": page,
            "page_num": page_num,
            "total": total,
            "keyword": keyword,
        })

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
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [_category_item(row) for row in rows],
            "page": page,
            "page_num": page_num,
            "total": total,
        })

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
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "分类已创建",
            "item": _category_item(item),
        })

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
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "更新成功",
            "item": _category_item(row) if row else None,
        })

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
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [_software_item(row, names.get(row.category_id, "")) for row in rows],
            "page": page,
            "page_num": page_num,
            "total": total,
        })

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
        link_error = _validate_links(links)
        if link_error:
            return _invalid(link_error)
        now = datetime.datetime.now()
        item = Software(
            category_id=category.id,
            name=name,
            summary=summary,
            cover_url=cover_url,
            version=version,
            links=links,
            status=1 if int(request_body.status or 0) == 1 else 0,
            sort=int(request_body.sort or 0),
            insert_time=now,
            update_time=now,
        )
        common.db.add(item)
        common.db.commit()
        common.db.refresh(item)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "软件已创建",
            "item": _software_item(item, category.name or ""),
        })

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
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "更新成功",
            "item": _software_item(row, category_name) if row else None,
        })


software_service = SoftwareService()
