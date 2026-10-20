from fastapi.responses import JSONResponse

from utils.public_exception import UnicornException


def register_exception_handlers(app):
    @app.exception_handler(UnicornException)
    async def unicorn_exception_handler(request, exc: UnicornException):
        return JSONResponse(
            {
                "code": exc.code,
                "codeMsg": exc.codeMsg
            }
        )
