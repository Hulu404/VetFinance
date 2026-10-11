"""Supabase JWT verification: asymmetric keys via JWKS, HS256 with a shared secret as fallback."""

from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient

from app.errors import unauthorized
from app.settings import Settings, get_settings

ASYMMETRIC_ALGS = ["RS256", "ES256", "EdDSA"]
_jwks_clients: dict[str, PyJWKClient] = {}


@dataclass(frozen=True)
class Principal:
    user_id: str
    claims: dict[str, Any]


def _jwks_client(supabase_url: str) -> PyJWKClient:
    url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(url, cache_keys=True, lifespan=600)
        _jwks_clients[url] = client
    return client


def verify_token(token: str, settings: Settings) -> Principal:
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
        if alg == "HS256":
            secret = settings.supabase_jwt_secret.get_secret_value()
            if not secret:
                raise unauthorized("Недействительный токен.")
            key: Any = secret
            algorithms = ["HS256"]
        elif alg in ASYMMETRIC_ALGS and settings.supabase_url:
            key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
            algorithms = ASYMMETRIC_ALGS
        else:
            raise unauthorized("Недействительный токен.")
        claims = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=settings.jwt_audience,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise unauthorized("Недействительный или просроченный токен.") from exc
    return Principal(user_id=str(claims["sub"]), claims=claims)


def get_principal(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized()
    return verify_token(token.strip(), settings)
