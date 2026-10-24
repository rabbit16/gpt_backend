"""软件商城：官方项目 + 用户提交审核。

契约以前端 ``src/request/projects.ts``（chatgpt-web feature/dev 分支）为准：
* ``GET  /open-source/projects``      公开列表，只出 approved
* ``GET  /open-source/my-projects``   我的提交，含待审核
* ``POST /open-source/projects``      提交新项目 / 新版本，进待审队列
* ``GET  /admin/open-source/projects`` 后台列表，可按状态过滤
* ``POST /admin/open-source/review``  通过 / 驳回

公开列表里永远先放「余额兔」这个官方条目：前端在接口失败时也会兜底展示它，
这里放一份真实数据，保证接口通了以后页面内容不缩水。
"""

from api.admin.auth import require_admin, resolve_login_user
from api.open_source.schemas import ProjectReview, ProjectSubmit
from api.users.models import OpenSourceProject, OpenSourceRelease, User
from app.http import json_response
from settings.database import engine
from utils.res_code import Code, ERROR_MAP

PLATFORMS = ("windows", "macos", "linux")
PROJECT_STATUS = ("pending", "approved", "rejected")
RELEASE_STATUS = ("pending", "approved", "rejected")

MIN_NAME = 2
MAX_NAME = 200
MIN_SUMMARY = 2
MAX_SUMMARY = 500
MAX_DESCRIPTION = 20000
MAX_URL = 900
MAX_VERSION = 50
MAX_CHANGELOG = 5000
MAX_NOTE = 500

OFFICIAL_NAME = "余额兔"
OFFICIAL_REPO = "https://github.com/rabbit16/chatgpt-web/tree/feature/dev/open-source/yuebao"
OFFICIAL_COVER = "/covers/yuebao.svg"
OFFICIAL_SUMMARY = "桌面小宠物，抬头就能看到余额和最近用量，不用再登录网页查。"
OFFICIAL_DESCRIPTION = (
    "常驻托盘的小兔子：鼠标移上去显示当前余额、今日消耗 token、本月消费；"
    "余额低于你设的阈值会提醒。只读取你自己的密钥，不做任何上传。"
)
OFFICIAL_RELEASES = [
    {
        "platform": "windows",
        "version": "1.3.0",
        "file_url": "https://raw.githubusercontent.com/rabbit16/chatgpt-web/feature/dev/public/downloads/yuebao-v1.3.0-windows.zip",
        "file_size": "414 KB",
        "changelog": "免安装版，解压后直接运行；修复托盘余额刷新延迟。",
    },
    {
        "platform": "macos",
        "version": "1.3.0",
        "file_url": "https://raw.githubusercontent.com/rabbit16/chatgpt-web/feature/dev/public/downloads/yuebao-v1.3.0-macos.zip",
        "file_size": "1.1 MB",
        "changelog": "与 Windows 版同步到 1.3.0；解压后拖入「应用程序」，首次打开需在「隐私与安全性」中允许。",
    },
    {
        "platform": "linux",
        "version": "1.1.0",
        "file_url": "https://raw.githubusercontent.com/rabbit16/chatgpt-web/feature/dev/public/downloads/yuebao-v1.1.0-linux.zip",
        "file_size": "70 KB",
        "changelog": "Linux 版：解压后运行 install.sh 安装，卸载运行 uninstall.sh。",
    },
]


def ensure_open_source_tables():
    OpenSourceProject.__table__.create(bind=engine, checkfirst=True)
    OpenSourceRelease.__table__.create(bind=engine, checkfirst=True)


def _fmt_time(value):
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or ""


def _ok(**payload):
    return json_response({
        "code": str(Code.OK),
        "codeMsg": ERROR_MAP[Code.OK],
        **payload,
    })


def _fail(code, message):
    return json_response({"code": str(code), "codeMsg": message})


def _official_project():
    return {
        "id": "balance-bunny",
        "name": OFFICIAL_NAME,
        "summary": OFFICIAL_SUMMARY,
        "description": OFFICIAL_DESCRIPTION,
        "repo_url": OFFICIAL_REPO,
        "author_name": "anyGPT 官方",
        "official": True,
        "status": "approved",
        "cover_url": OFFICIAL_COVER,
        "updated_at": "",
        "releases": [
            {
                "id": "bb-%s" % item["platform"],
                "version": item["version"],
                "platform": item["platform"],
                "file_url": item["file_url"],
                "file_size": item["file_size"],
                "changelog": item["changelog"],
                "status": "approved",
                "created_at": "2026-10-20 21:18",
            }
            for item in OFFICIAL_RELEASES
        ],
    }


def _release_item(row: OpenSourceRelease):
    return {
        "id": row.id,
        "version": row.version or "",
        "platform": row.platform or "",
        "file_url": row.file_url or "",
        "file_size": row.file_size or "",
        "changelog": row.changelog or "",
        "status": row.status or "pending",
        "created_at": _fmt_time(row.created_at),
        "reviewer_note": row.reviewer_note or "",
    }


def _project_item(row: OpenSourceProject, releases):
    return {
        "id": row.id,
        "name": row.name or "",
        "summary": row.summary or "",
        "description": row.description or "",
        "repo_url": row.repo_url or "",
        "author_name": row.author_name or "",
        "official": bool(row.official),
        "cover_url": row.cover_url or "",
        "status": row.status or "pending",
        "reviewer_note": row.reviewer_note or "",
        "user_id": row.user_id,
        "updated_at": _fmt_time(row.updated_at),
        "releases": releases,
    }


def _group_releases(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.project_id, []).append(_release_item(row))
    order = {name: index for index, name in enumerate(PLATFORMS)}
    for items in grouped.values():
        items.sort(key=lambda item: (order.get(item["platform"], 99), item["id"]))
    return grouped


def _is_url(value):
    lowered = (value or "").strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _approve_existing(db, name):
    """同一项目名再次提交通过时，把旧版本的安装包标记为过期，避免同一平台出现两个下载入口。"""
    row = db.query(OpenSourceProject).filter(
        OpenSourceProject.name == name,
        OpenSourceProject.status == "approved",
    ).first()
    if not row:
        return
    db.query(OpenSourceRelease).filter(
        OpenSourceRelease.project_id == row.id,
        OpenSourceRelease.status == "approved",
    ).update({OpenSourceRelease.status: "rejected",
              OpenSourceRelease.reviewer_note: "已被新版本替代"}, synchronize_session=False)


class OpenSourceService:
    # ---------------- 公开 / 用户端 ----------------

    def list_public(self, common):
        ensure_open_source_tables()
        rows = common.db.query(OpenSourceProject).filter(
            OpenSourceProject.status == "approved",
        ).order_by(OpenSourceProject.updated_at.desc(), OpenSourceProject.id.desc()).all()

        releases = []
        if rows:
            releases = common.db.query(OpenSourceRelease).filter(
                OpenSourceRelease.project_id.in_([row.id for row in rows]),
                OpenSourceRelease.status == "approved",
            ).all()
        grouped = _group_releases(releases)

        items = [_official_project()]
        for row in rows:
            items.append(_project_item(row, grouped.get(row.id, [])))
        return _ok(items=items, list=items)

    def list_mine(self, common):
        ensure_open_source_tables()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])

        rows = common.db.query(OpenSourceProject).filter(
            OpenSourceProject.user_id == user.user_id,
        ).order_by(OpenSourceProject.updated_at.desc(), OpenSourceProject.id.desc()).all()

        releases = []
        if rows:
            releases = common.db.query(OpenSourceRelease).filter(
                OpenSourceRelease.project_id.in_([row.id for row in rows]),
            ).all()
        grouped = _group_releases(releases)
        items = [_project_item(row, grouped.get(row.id, [])) for row in rows]
        return _ok(items=items, list=items)

    def submit(self, request_body: ProjectSubmit, common):
        ensure_open_source_tables()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])

        name = (request_body.name or "").strip()
        summary = (request_body.summary or "").strip()
        description = (request_body.description or "").strip()
        repo_url = (request_body.repo_url or "").strip()
        version = (request_body.version or "").strip()
        changelog = (request_body.changelog or "").strip()
        cover_url = (request_body.cover_url or "").strip()

        if not (MIN_NAME <= len(name) <= MAX_NAME):
            return _fail(Code.PROJECT_INVALID, "项目名请控制在 %s-%s 字" % (MIN_NAME, MAX_NAME))
        if not (MIN_SUMMARY <= len(summary) <= MAX_SUMMARY):
            return _fail(Code.PROJECT_INVALID, "一句话介绍请控制在 %s-%s 字" % (MIN_SUMMARY, MAX_SUMMARY))
        if len(description) > MAX_DESCRIPTION:
            return _fail(Code.PROJECT_INVALID, "详细介绍过长")
        if repo_url and not _is_url(repo_url):
            return _fail(Code.PROJECT_INVALID, "仓库地址请填写 http:// 或 https:// 开头的链接")
        if len(version) > MAX_VERSION:
            return _fail(Code.PROJECT_INVALID, "版本号请控制在 %s 字以内" % MAX_VERSION)
        if len(changelog) > MAX_CHANGELOG:
            return _fail(Code.PROJECT_INVALID, "更新说明过长")

        releases = []
        for item in request_body.releases or []:
            platform = (item.platform or "").strip().lower()
            file_url = (item.file_url or "").strip()
            if platform not in PLATFORMS:
                return _fail(Code.PROJECT_INVALID, "平台只支持 Windows / macOS / Linux")
            if not file_url:
                continue
            if not _is_url(file_url) or len(file_url) > MAX_URL:
                return _fail(Code.PROJECT_INVALID, "安装包地址请填写 http:// 或 https:// 开头的链接")
            if platform in [row["platform"] for row in releases]:
                return _fail(Code.PROJECT_INVALID, "同一平台只能提交一个安装包")
            releases.append({"platform": platform, "file_url": file_url})

        if not releases:
            return _fail(Code.PROJECT_INVALID, "至少填一个平台的安装包地址，站长才审得动")

        # 同一用户重复提交同名项目：合并成新版本，走一次审核
        project = common.db.query(OpenSourceProject).filter(
            OpenSourceProject.user_id == user.user_id,
            OpenSourceProject.name == name,
        ).order_by(OpenSourceProject.id.desc()).first()

        if project:
            project.summary = summary
            project.description = description or project.description
            project.repo_url = repo_url or project.repo_url
            project.cover_url = cover_url or project.cover_url
            project.status = "pending"
            project.reviewer_note = ""
        else:
            author = (user.name or "").strip() or str(user.telephone or "")
            project = OpenSourceProject(
                name=name,
                summary=summary,
                description=description,
                repo_url=repo_url,
                cover_url=cover_url,
                author_name=author,
                official=False,
                status="pending",
                user_id=user.user_id,
            )
            common.db.add(project)
            common.db.flush()

        for item in releases:
            common.db.add(OpenSourceRelease(
                project_id=project.id,
                version=version,
                platform=item["platform"],
                file_url=item["file_url"],
                changelog=changelog,
                status="pending",
            ))

        common.db.commit()
        common.db.refresh(project)
        return _ok(data={"id": project.id}, id=project.id, message="已提交，等待站长审核")

    # ---------------- 站长端 ----------------

    def admin_list(self, request_body, common):
        _, error = require_admin(common)
        if error:
            return error
        ensure_open_source_tables()

        page = getattr(request_body, "page", 1) or 1
        page_num = getattr(request_body, "page_num", 20) or 20
        page_num = min(max(page_num, 1), 50)
        status = (getattr(request_body, "status", "") or "").strip()

        query = common.db.query(OpenSourceProject)
        if status and status != "all":
            if status not in PROJECT_STATUS:
                return _fail(Code.PROJECT_INVALID, "状态参数不正确")
            query = query.filter(OpenSourceProject.status == status)

        total = query.count()
        rows = query.order_by(
            OpenSourceProject.updated_at.desc(), OpenSourceProject.id.desc()
        ).offset((page - 1) * page_num).limit(page_num).all()

        releases = []
        if rows:
            releases = common.db.query(OpenSourceRelease).filter(
                OpenSourceRelease.project_id.in_([row.id for row in rows]),
            ).all()
        grouped = _group_releases(releases)

        user_ids = {row.user_id for row in rows if row.user_id}
        names = {}
        if user_ids:
            for item in common.db.query(User.user_id, User.name, User.telephone).filter(
                User.user_id.in_(user_ids)
            ).all():
                names[item.user_id] = (item.name or "").strip() or str(item.telephone or "")

        items = []
        for row in rows:
            item = _project_item(row, grouped.get(row.id, []))
            item["user_name"] = names.get(row.user_id, "")
            items.append(item)

        return _ok(data={"list": items, "total": total, "page": page}, list=items, total=total, page=page)

    def review(self, request_body: ProjectReview, common):
        _, error = require_admin(common)
        if error:
            return error
        ensure_open_source_tables()

        action = (request_body.action or "").strip()
        if action not in ("approve", "reject"):
            return _fail(Code.PROJECT_INVALID, "审核动作只能是 approve 或 reject")
        note = (request_body.note or "").strip()[:MAX_NOTE]

        project = common.db.query(OpenSourceProject).filter(
            OpenSourceProject.id == request_body.id
        ).first()
        if not project:
            return _fail(Code.PROJECT_INVALID, "项目不存在")
        if project.official:
            return _fail(Code.ACCESS_DENY, "官方预置项目不需要审核")

        if action == "approve":
            _approve_existing(common.db, project.name)
            project.status = "approved"
            project.reviewer_note = ""
            common.db.query(OpenSourceRelease).filter(
                OpenSourceRelease.project_id == project.id,
                OpenSourceRelease.status == "pending",
            ).update({OpenSourceRelease.status: "approved"}, synchronize_session=False)
        else:
            project.status = "rejected"
            project.reviewer_note = note
            common.db.query(OpenSourceRelease).filter(
                OpenSourceRelease.project_id == project.id,
                OpenSourceRelease.status == "pending",
            ).update({OpenSourceRelease.status: "rejected",
                      OpenSourceRelease.reviewer_note: note}, synchronize_session=False)

        common.db.commit()
        return _ok(data={"id": project.id}, id=project.id)


open_source_service = OpenSourceService()
