import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.users.curd import generate_file
from api.users.models import User, UserContext
from settings.dependencies import CommonQueryParams
from settings.macro import FILE_STORE_LINUX_PWD, USR_LOG
from utils.public_exception import UnicornException

router = APIRouter()

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MEDIA = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class ExportFileBody(BaseModel):
    userId: int = Field(..., description="用户Id")
    content: str = Field(..., description="要导出的文档内容")
    file_type: str = Field("docx", description="导出类型，如 docx")
    filename: str = Field("document.docx", description="下载文件名")
    source_format: str = Field("markdown", description="markdown 或 html")


def _safe_filename(filename: str, file_type: str):
    name = Path(filename or "document").name
    if not name or name in {".", ".."}:
        name = "document"
    suffix = f".{file_type.lstrip('.')}"
    if not name.lower().endswith(suffix.lower()):
        name = f"{name}{suffix}"
    return name


def _media_type(file_type: str):
    if file_type == "docx":
        return DOCX_MEDIA
    if file_type == "pptx":
        return PPTX_MEDIA
    return None


@router.get("/file/image")
def download_image(
        filename: str = Query(...),
        common: CommonQueryParams = Depends()):
    file_path = Path(FILE_STORE_LINUX_PWD) / "draw" / filename
    if not file_path.exists():
        raise UnicornException(404, "image not found")
    return FileResponse(file_path, filename=filename,
                        media_type="image/png",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/file")
def download_file(
    user_id: int = Query(...),
    filename: str = Query(...),
    file_type: str = Query(...),
    context_id: str = Query(...),
    chat_index: int = Query(...),
    common: CommonQueryParams = Depends()):
    try:
        user = common.db.query(User).filter(User.user_id == user_id).first()
        context_item = common.db.query(UserContext).filter(UserContext.context_id == context_id).first()
        content = json.loads(context_item.context)[chat_index]
        if not user:
            raise UnicornException(
                404,
                "no user"
            )
        filename = _safe_filename(filename, file_type)
        file_path = Path(FILE_STORE_LINUX_PWD) / str(user_id) / filename
        generate_file(content, user_id, filename, file_type)
        return FileResponse(
            file_path,
            filename=filename,
            media_type=_media_type(file_type),
            headers={"Content-Disposition": "attachment; filename=" + filename},
        )
    except UnicornException:
        raise
    except Exception as e:
        USR_LOG.warning(f"""创建文件失败 {e.__repr__()}""")
        raise UnicornException(
            400,
            "创建文件失败，请检查文件内容"
        )


@router.post("/file/export")
def export_file(body: ExportFileBody, common: CommonQueryParams = Depends()):
    try:
        user = common.db.query(User).filter(User.user_id == body.userId).first()
        if not user:
            raise UnicornException(404, "no user")
        file_type = (body.file_type or "docx").lower()
        filename = _safe_filename(body.filename, file_type)
        generate_file(
            {"gpt": body.content},
            body.userId,
            filename,
            file_type,
            source_format=body.source_format or "markdown",
        )
        file_path = Path(FILE_STORE_LINUX_PWD) / str(body.userId) / filename
        if not file_path.exists():
            raise UnicornException(400, "创建文件失败，请检查文件内容")
        return FileResponse(
            file_path,
            filename=filename,
            media_type=_media_type(file_type),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except UnicornException:
        raise
    except Exception as e:
        USR_LOG.warning(f"""导出文件失败 {e.__repr__()}""")
        raise UnicornException(
            400,
            "创建文件失败，请检查文件内容"
        )
