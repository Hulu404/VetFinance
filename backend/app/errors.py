"""Errors in the contract format: {"error": {"code", "message", "details"}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorDetailOut(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorBodyOut(BaseModel):
    """Every error of the API: {"error": {"code", "message", "details"}}."""

    error: ErrorDetailOut


_ERROR_TITLES = {
    401: "Нет или недействительный токен (`unauthorized`).",
    403: "Пользователь не привязан к клинике (`forbidden`).",
    404: "Не найдено или чужое (`not_found`).",
    409: "Конфликт состояния (`conflict`).",
    422: "Ошибка валидации (`validation`): `details.fields` или `details.reason`.",
    429: "Слишком часто (`rate_limited`), заголовок `Retry-After`.",
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` for a router or a route: the contract error body for each status."""
    return {c: {"model": ErrorBodyOut, "description": _ERROR_TITLES[c]} for c in codes}


class ApiError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.retry_after: int | None = None


def unauthorized(message: str = "Требуется вход в систему.") -> ApiError:
    return ApiError(401, "unauthorized", message)


def forbidden(message: str = "Нет доступа к клинике.") -> ApiError:
    return ApiError(403, "forbidden", message)


def not_found(message: str = "Не найдено.") -> ApiError:
    return ApiError(404, "not_found", message)


def conflict(message: str) -> ApiError:
    return ApiError(409, "conflict", message)


def rate_limited(message: str, retry_after: int) -> ApiError:
    error = ApiError(429, "rate_limited", message)
    error.retry_after = retry_after
    return error


def validation_fields(
    fields: dict[str, str], message: str = "Некорректные данные запроса."
) -> ApiError:
    """422 with per-field reason codes: details.fields = {"amount": "must_be_positive"}."""
    return ApiError(422, "validation", message, {"fields": fields})


def validation_reason(reason: str, message: str, **details: Any) -> ApiError:
    """422 about the whole request: details.reason = "unsupported_format"."""
    return ApiError(422, "validation", message, {"reason": reason, **details})


def _body(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


# pydantic error type -> reason code of the contract (details.fields)
_FIELD_REASONS = {
    "missing": "required",
    "string_too_short": "required",
    "greater_than": "must_be_positive",
    "greater_than_equal": "must_be_positive",
    "less_than_equal": "too_large",
    "less_than": "too_large",
    "string_too_long": "too_long",
    "int_from_float": "too_many_decimals",
    "extra_forbidden": "unknown_field",
}
_HTTP_CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        headers: dict[str, str] = {}
        if exc.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            _body(exc.code, exc.message, exc.details), status_code=exc.status_code, headers=headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(
            exc.status_code, "rate_limited" if exc.status_code == 429 else "validation"
        )
        message = "Не найдено." if exc.status_code == 404 else "Ошибка запроса."
        return JSONResponse(_body(code, message, {}), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for e in exc.errors():
            name = ".".join(str(p) for p in e["loc"][1:]) or "body"
            fields.setdefault(name, _FIELD_REASONS.get(e["type"], "invalid"))
        return JSONResponse(
            _body("validation", "Некорректные данные запроса.", {"fields": fields}),
            status_code=422,
        )
