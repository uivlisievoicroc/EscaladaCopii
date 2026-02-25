"""
Authentication/authorization dependencies for FastAPI routes.

These helpers implement the common access-control rules used across the API:
- Extract JWT from either Authorization header (legacy) or httpOnly cookie (preferred)
- Decode/validate JWT and expose its claims to route handlers
- For missing JWT, grant synthetic admin claims only for trusted network IPs
- Enforce role-based access (admin/judge/viewer/spectator)
- Enforce per-box access for roles that are scoped to specific boxes

Claims shape (see `escalada.auth.service.create_access_token`):
- `sub`: username (string)
- `role`: "admin" | "judge" | "viewer" | "spectator"
- `boxes`: list[int] of allowed box ids (may be empty = no restriction for some roles)
"""

# -------------------- Standard library imports --------------------
import os
import re
import socket
from functools import lru_cache
from ipaddress import ip_address
from typing import Any, Dict, Iterable, Optional

# -------------------- Third-party imports --------------------
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

# -------------------- Local application imports --------------------
from escalada.auth.service import decode_token
from escalada.security import admin_session, license_events, usb_license

# psutil is an optional dependency here; we use it for robust local interface IP discovery.
try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    psutil = None

# Cookie name must match auth.py
COOKIE_NAME = "escalada_token"
DEFAULT_ADMIN_TRUSTED_IPS = frozenset({"127.0.0.1", "::1", "localhost"})

# OAuth2PasswordBearer provides the "Authorization: Bearer <token>" parsing.
# We set `auto_error=False` so cookie auth can be used as a fallback without FastAPI
# raising a 401 before our custom logic runs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
ADMIN_MUTATING_COMMAND_TYPES = {
    "START_TIMER",
    "STOP_TIMER",
    "RESUME_TIMER",
    "PROGRESS_UPDATE",
    "SUBMIT_SCORE",
    "INIT_ROUTE",
    "SET_TIMER_PRESET",
    "SET_TIME_CRITERION",
    "SET_TIME_TIEBREAK_DECISION",
    "SET_PREV_ROUNDS_TIEBREAK_DECISION",
    "REGISTER_TIME",
    "TIMER_SYNC",
    "RESET_BOX",
    "RESET_PARTIAL",
    "ACTIVE_CLIMBER",
}


def _parse_admin_trusted_ips(raw: str | None) -> set[str]:
    if raw is None:
        return set(DEFAULT_ADMIN_TRUSTED_IPS)
    values = {entry.strip().lower() for entry in raw.split(",") if entry.strip()}
    return values or set(DEFAULT_ADMIN_TRUSTED_IPS)


@lru_cache(maxsize=1)
def _get_local_interface_ips() -> set[str]:
    """
    Return a set of IPs assigned to the local machine.

    This allows the host laptop to be treated as a trusted admin even when accessing
    the server via its LAN IP address (packaged runs do not rely on a repo `.env`).
    """
    ips: set[str] = set()

    if psutil is not None:
        try:
            for addresses in psutil.net_if_addrs().values():
                for addr in addresses:
                    if addr.family not in (socket.AF_INET, socket.AF_INET6):
                        continue
                    raw = str(getattr(addr, "address", "") or "").strip()
                    if not raw:
                        continue
                    # On some platforms IPv6 link-local addresses include a scope id (e.g. "%en0").
                    raw = raw.split("%", 1)[0]
                    try:
                        parsed = ip_address(raw)
                    except ValueError:
                        continue
                    if parsed.is_unspecified:
                        continue
                    ips.add(raw.lower())
        except Exception:
            pass

    # Fallback: best-effort default outbound interface IP (single address).
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            if local_ip:
                ips.add(str(local_ip).strip().lower())
        finally:
            sock.close()
    except Exception:
        pass

    return ips


def is_trusted_admin_ip(host: str | None) -> bool:
    normalized_host = (host or "").strip().lower()
    if not normalized_host:
        return False
    trusted_ips = _parse_admin_trusted_ips(os.getenv("ADMIN_TRUSTED_IPS"))
    if normalized_host in trusted_ips:
        return True
    return normalized_host in _get_local_interface_ips()


def _parse_box_id(value: Any) -> int | None:
    """Parse box id safely; return None for missing/invalid values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_JWT_LIKE_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


def _looks_like_jwt(token: str | None) -> bool:
    normalized = (token or "").strip()
    if not normalized:
        return False
    return bool(_JWT_LIKE_RE.match(normalized))


async def get_token_from_request(
    request: Request,
    header_token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[str]:
    """
    Extract JWT token from:
    1. httpOnly cookie - preferred for XSS protection
    2. Authorization header (Bearer token) - backwards compatibility
    """
    # Prefer cookie auth so Authorization can carry USB admin session tokens.
    cookie_token = request.cookies.get(COOKIE_NAME)
    if cookie_token:
        return cookie_token

    # Backwards compatible fallback to Authorization bearer JWT.
    # Note: Admin USB sessions also use `Authorization: Bearer ...`. Only treat it as a JWT when
    # it matches the expected 3-part JWT shape; otherwise allow trusted-IP admin to kick in.
    if header_token and _looks_like_jwt(header_token):
        return header_token

    return None


async def get_current_claims(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
) -> Dict[str, Any]:
    """
    Decode the JWT and return its claims.

    `decode_token()` raises HTTPException for invalid/expired tokens; those propagate to the client.
    """
    if token:
        return decode_token(token)

    peer = request.client.host if request.client else None
    if is_trusted_admin_ip(peer):
        return {"sub": "trusted-admin", "role": "admin", "boxes": []}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="not_authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(allowed: Iterable[str]):
    """
    Dependency factory: enforce that the current user has one of the allowed roles.

    Usage:
        @router.get(...)
        async def endpoint(claims=Depends(require_role(["admin"]))):
            ...
    """
    async def checker(claims: Dict[str, Any] = Depends(get_current_claims)) -> Dict[str, Any]:
        role = claims.get("role")
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="forbidden_role",
            )
        return claims

    return checker


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return None
    token = authorization_header[len(prefix):].strip()
    return token or None


async def _enforce_admin_usb_security(request: Request) -> None:
    usb_token = _extract_bearer_token(request.headers.get("Authorization"))
    if not usb_token or not await admin_session.is_token_valid(usb_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "ADMIN_SESSION_REQUIRED",
                "reason": "invalid_or_missing_admin_session",
            },
        )

    license_status = usb_license.check_license()
    if not license_status.get("valid"):
        was_locked = await admin_session.lock()
        if was_locked:
            await license_events.publish(
                "admin_locked",
                {
                    "reason": "license_invalid",
                    "license_reason": license_status.get("reason"),
                },
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "LICENSE_REQUIRED",
                "reason": license_status.get("reason"),
            },
        )


async def require_admin_action(
    request: Request,
    claims: Dict[str, Any] = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Require admin RBAC plus USB admin session + valid license."""
    await _enforce_admin_usb_security(request)
    return claims


async def require_admin_command_action(
    request: Request,
    claims: Dict[str, Any],
    command_type: str | None,
) -> None:
    """Require USB lock only for admin mutating /api/cmd calls."""
    if claims.get("role") != "admin":
        return
    normalized_type = (command_type or "").strip().upper()
    if normalized_type not in ADMIN_MUTATING_COMMAND_TYPES:
        return
    await _enforce_admin_usb_security(request)


async def require_box_access(
    request: Request,
    claims: Dict[str, Any] = Depends(require_role(["judge", "admin"])),
) -> Dict[str, Any]:
    """
    Validate that the caller can operate on the requested box.
    Works for body-based commands that include boxId or path params `box_id`.
    """
    # Admins can access all boxes.
    if claims.get("role") == "admin":
        return claims

    # Judges are scoped to an allow-list of boxes.
    allowed_boxes = set(claims.get("boxes") or [])
    box_id = None

    # Try to extract boxId from JSON body if available
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            # `Request.json()` is safe to call here; Starlette caches the body for subsequent reads.
            body = await request.json()
            box_id = body.get("boxId") if isinstance(body, dict) else None
        except Exception:
            box_id = None

    # Fallback to path parameter for GET state/{box_id}
    if box_id is None:
        box_id = request.path_params.get("box_id")

    parsed_box_id = _parse_box_id(box_id)
    if parsed_box_id is None or parsed_box_id not in allowed_boxes:
        # If box id is missing or outside the allow-list, reject with a consistent error code.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden_box",
        )

    return claims


async def require_view_access(
    claims: Dict[str, Any] = Depends(require_role(["viewer", "judge", "admin"])),
) -> Dict[str, Any]:
    """Allow any authenticated non-spectator viewer (viewer/judge/admin)."""
    return claims


def require_view_box_access(param_name: str = "box_id"):
    """
    Allow viewer/judge/admin; if boxes are specified in claims, enforce membership.
    Admin bypasses box checks.
    """

    async def checker(
        request: Request,
        claims: Dict[str, Any] = Depends(require_role(["viewer", "judge", "admin"])),
    ) -> Dict[str, Any]:
        # Admins can view any box.
        if claims.get("role") == "admin":
            return claims

        allowed_boxes = set(claims.get("boxes") or [])
        box_id = _parse_box_id(request.path_params.get(param_name))

        # If caller has an explicit allow-list, enforce membership
        if allowed_boxes and (box_id is None or box_id not in allowed_boxes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="forbidden_box",
            )
        return claims

    return checker
