"""Read-only client of the Vetmanager REST API.

NOTE: the endpoints, headers and the filter syntax follow the Vetmanager REST API as remembered; they
have not been run against a real account yet and must be checked on the first one. The client only
reads and never logs the API key or response bodies (they contain data of pet owners).
"""

import json
import logging
from datetime import date
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 2000
INVOICE_CHUNK = 50
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
OK = "ok"
INVALID_KEY = "invalid_key"
UNREACHABLE = "unreachable"
RATE_LIMITED = "rate_limited"
UNKNOWN = "unknown"
_UNAUTHORIZED = (401, 403)
_RATE_LIMIT = 429
_SERVER_ERROR = 500


class VetmanagerError(Exception):
    """A failed call; `code` is one of the sync error codes of the contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VetmanagerApi(Protocol):
    async def ping(self, host: str, key: str) -> str:
        """`ok`, `invalid_key`, `unreachable` or `rate_limited`."""
        ...

    async def fetch(self, host: str, key: str, since: date) -> dict[str, dict[str, Any]]:
        """Raw responses by entity, in the shape `{"data": {"<entity>": [...]}}`."""
        ...


def _filter(prop: str, operator: str, value: Any) -> str:
    return json.dumps([{"property": prop, "value": value, "operator": operator}])


class HttpVetmanagerApi:
    async def ping(self, host: str, key: str) -> str:
        try:
            async with self._client(host, key) as client:
                response = await client.get("user", params={"limit": 1})
        except httpx.HTTPError:
            return UNREACHABLE
        if response.status_code in _UNAUTHORIZED:
            return INVALID_KEY
        if response.status_code == _RATE_LIMIT:
            return RATE_LIMITED
        return OK if response.is_success else UNREACHABLE

    async def fetch(self, host: str, key: str, since: date) -> dict[str, dict[str, Any]]:
        since_text = since.isoformat()
        raw: dict[str, dict[str, Any]] = {}
        async with self._client(host, key) as client:
            for entity in ("user", "good", "cassa"):
                raw[entity] = await self._collect(client, entity, None)
            raw["admission"] = await self._collect(
                client, "admission", _filter("admission_date", ">=", since_text)
            )
            raw["invoice"] = await self._collect(
                client, "invoice", _filter("invoice_date", ">=", since_text)
            )
            raw["payment"] = await self._collect(
                client, "payment", _filter("create_date", ">=", since_text)
            )
            raw["invoiceDocument"] = await self._documents(client, raw["invoice"])
        return raw

    @staticmethod
    def _client(host: str, key: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"https://{host}/rest/api/",
            headers={"X-REST-API-KEY": key, "Accept": "application/json"},
            timeout=TIMEOUT,
            follow_redirects=False,
        )

    async def _documents(
        self, client: httpx.AsyncClient, invoices: dict[str, Any]
    ) -> dict[str, Any]:
        ids = [str(i["id"]) for i in invoices.get("data", {}).get("invoice", []) if "id" in i]
        items: list[Any] = []
        for start in range(0, len(ids), INVOICE_CHUNK):
            chunk = ids[start : start + INVOICE_CHUNK]
            part = await self._collect(
                client, "invoiceDocument", _filter("invoice_id", "IN", chunk)
            )
            items.extend(part["data"]["invoiceDocument"])
        return {"data": {"totalCount": str(len(items)), "invoiceDocument": items}}

    async def _collect(
        self, client: httpx.AsyncClient, entity: str, filter_json: str | None
    ) -> dict[str, Any]:
        items: list[Any] = []
        offset = 0
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"limit": PAGE_SIZE, "offset": offset}
            if filter_json:
                params["filter"] = filter_json
            page = await self._get(client, entity, params)
            data = page.get("data")
            batch = data.get(entity) if isinstance(data, dict) else None
            if not isinstance(batch, list):
                raise VetmanagerError(UNKNOWN)
            items.extend(batch)
            offset += PAGE_SIZE
            if len(batch) < PAGE_SIZE:
                break
        return {"data": {"totalCount": str(len(items)), entity: items}}

    @staticmethod
    async def _get(
        client: httpx.AsyncClient, entity: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = await client.get(entity, params=params)
        except httpx.HTTPError as exc:
            logger.warning("vetmanager %s: %s", entity, type(exc).__name__)
            raise VetmanagerError(UNREACHABLE) from exc
        if response.status_code in _UNAUTHORIZED:
            raise VetmanagerError(INVALID_KEY)
        if response.status_code == _RATE_LIMIT:
            raise VetmanagerError(RATE_LIMITED)
        if response.status_code >= _SERVER_ERROR:
            raise VetmanagerError(UNREACHABLE)
        if not response.is_success:
            logger.warning("vetmanager %s: HTTP %s", entity, response.status_code)
            raise VetmanagerError(UNKNOWN)
        try:
            body = response.json()
        except ValueError as exc:
            raise VetmanagerError(UNKNOWN) from exc
        if not isinstance(body, dict):
            raise VetmanagerError(UNKNOWN)
        return body


def get_vetmanager_api() -> VetmanagerApi:
    return HttpVetmanagerApi()
