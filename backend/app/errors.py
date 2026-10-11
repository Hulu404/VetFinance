"""Errors in the contract format: {"error": {"code", "message", "details"}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def unauthorized(message: str = "Требуется вход в систему.") -> ApiError:
    return ApiError(401, "unauthorized", message)


def forbidden(message: str = "Нет доступа к клинике.") -> ApiError:
    return ApiError(403, "forbidden", message)


def _body(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


_HTTP_CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            _body(exc.code, exc.message, exc.details),
            status_code=exc.status_code,
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "validation")
        message = "Не найдено." if exc.status_code == 404 else "Ошибка запроса."
        return JSONResponse(_body(code, message, {}), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "problem": e["type"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            _body("validation", "Некорректные данные запроса.", {"fields": fields}),
            status_code=422,
        )
