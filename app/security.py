from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

from app.config import Settings, get_settings


@dataclass(frozen=True)
class AuthUser:
    oid: Optional[str]
    email: Optional[str]
    roles: set[str]
    claims: dict[str, Any]


_jwks_clients: dict[str, PyJWKClient] = {}


def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = authorization.split(" ", 1)[1].strip()
    if settings.auth_disabled and token == settings.auth_disabled_token:
        return AuthUser(
            oid="local-auth-disabled",
            email="local@example.com",
            roles={"admin"},
            claims={},
        )

    try:
        jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        ) from exc

    if not settings.azure_jwks_url or not settings.azure_client_ids:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    try:
        jwks_client = _get_jwks_client(
            settings.azure_jwks_url,
            settings.auth_jwks_timeout_seconds,
        )
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.azure_client_ids,
            issuer=settings.azure_issuer,
            options={"require": ["exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        ) from exc

    roles = _extract_roles(claims)
    return AuthUser(
        oid=claims.get("oid") or claims.get("sub"),
        email=claims.get("preferred_username") or claims.get("email") or claims.get("upn"),
        roles=roles,
        claims=claims,
    )


def require_dashboard_role(
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    allowed = settings.allowed_role_set
    if not {role.lower() for role in user.roles}.intersection(allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )
    return user


def require_kfc_reporte_role(
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    """Reporte KFC · Autorápido y Helados: solo el rol `kfchiden` (KFC_REPORTE_ROLES), no Planners/admin."""
    allowed = settings.kfc_reporte_role_set
    if not {role.lower() for role in user.roles}.intersection(allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )
    return user


def _get_jwks_client(url: str, timeout_seconds: float) -> PyJWKClient:
    cache_key = f"{url}|{timeout_seconds}"
    if cache_key not in _jwks_clients:
        _jwks_clients[cache_key] = PyJWKClient(url, timeout=timeout_seconds)
    return _jwks_clients[cache_key]


def _extract_roles(claims: dict[str, Any]) -> set[str]:
    raw_roles: list[str] = []
    for key in ("roles", "role", "groups"):
        value = claims.get(key)
        if isinstance(value, str):
            raw_roles.extend(part.strip() for part in value.replace(",", " ").split())
        elif isinstance(value, list):
            raw_roles.extend(str(part).strip() for part in value)
    return {role for role in raw_roles if role}
