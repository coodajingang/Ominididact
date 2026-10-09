import os
import secrets
import logging
from typing import Optional, Any

logger = logging.getLogger("auth")

def _load_env_file() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            logger.warning(f"Failed to load .env file: {e}")

_load_env_file()

try:
    from fastapi import Request, HTTPException, Security, Depends
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    security_bearer = HTTPBearer(auto_error=False)
except ImportError:
    class HTTPException(Exception):
        def __init__(self, status_code: int = 400, detail: str = "", headers: Optional[dict] = None):
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}
            super().__init__(detail)

    class Request:
        pass

    class HTTPAuthorizationCredentials:
        credentials: str = ""

    def Depends(fn):
        return None

    security_bearer = None

def get_api_token() -> Optional[str]:
    """
    Returns the configured API token from environment variable OMNIDIDACT_API_TOKEN or API_TOKEN.
    If not set or empty, authentication is disabled (local/development mode).
    """
    token = os.getenv("OMNIDIDACT_API_TOKEN") or os.getenv("API_TOKEN")
    if token:
        token = token.strip()
    return token if token else None

def is_auth_required() -> bool:
    """Returns whether API token authentication is currently required."""
    return get_api_token() is not None

def verify_token_string(provided_token: Optional[str]) -> bool:
    """
    Constant-time comparison between provided token and configured token.
    """
    expected = get_api_token()
    if not expected:
        return True
    if not provided_token:
        return False
    return secrets.compare_digest(provided_token.strip(), expected)

PUBLIC_HTML_PATHS = {
    "/",
    "/config",
    "/chat",
    "/study",
    "/study/flashcards",
    "/login",
    "/auth",
}

def extract_token_from_request(request: Request) -> Optional[str]:
    """
    Extracts the API token from Authorization header, X-API-Token, query parameters, or Cookies.
    """
    # 1. Bearer token from Authorization header
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        val = auth_header[7:].strip()
        if val:
            return val

    # 2. X-API-Token header
    x_token = request.headers.get("X-API-Token") or request.headers.get("x-api-token")
    if x_token and x_token.strip():
        return x_token.strip()

    # 3. Direct query parameter (for download / stream / initial links)
    query_token = request.query_params.get("token") or request.query_params.get("api_token")
    if query_token and query_token.strip():
        return query_token.strip()

    # 4. Secure Cookie (omnididact_token)
    if hasattr(request, "cookies"):
        cookie_token = (
            request.cookies.get("omnididact_token")
            or request.cookies.get("token")
            or request.cookies.get("api_token")
        )
        if cookie_token and cookie_token.strip():
            return cookie_token.strip()

    return None

def is_request_authenticated(request: Request) -> bool:
    """
    Returns True if authentication is disabled OR if the request presents a valid token.
    """
    expected = get_api_token()
    if not expected:
        return True
    token = extract_token_from_request(request)
    return verify_token_string(token)

def set_secure_auth_cookie(
    response: Any,
    token: str,
    remember: bool = True,
    request: Optional[Request] = None
) -> None:
    """
    Sets a hardened auth cookie for the user:
    - HttpOnly: True (completely blocks JavaScript/XSS token theft)
    - SameSite: "Lax" (defends against CSRF attacks while allowing top-level navigation)
    - Secure: True when running on HTTPS or behind an SSL reverse proxy
    - Path: "/" (valid for entire domain/origin)
    - Max-Age: 30 days if remember else None (session cookie)
    """
    is_secure = False
    if request:
        proto = request.headers.get("x-forwarded-proto", "").lower()
        is_secure = (request.url.scheme == "https") or (proto == "https")

    max_age = (30 * 86400) if remember else None
    response.set_cookie(
        key="omnididact_token",
        value=token.strip(),
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_secure
    )

def clear_auth_cookie(response: Any) -> None:
    """
    Securely deletes the auth cookie.
    """
    response.delete_cookie(
        key="omnididact_token",
        path="/",
        httponly=True,
        samesite="lax"
    )

async def verify_api_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> None:
    """
    FastAPI dependency that enforces API Token authentication when OMNIDIDACT_API_TOKEN is configured.
    """
    expected_token = get_api_token()
    if not expected_token:
        # Auth not configured -> Allow anonymous access
        return

    # Whitelisted frontend entrypoints serve the HTML/SPA shell or redirect to /login
    if hasattr(request, "url") and request.url.path in PUBLIC_HTML_PATHS:
        return

    # 1. Check Bearer token from Authorization header
    token = credentials.credentials if credentials else None

    # 2. Fallback check for X-API-Token or direct query parameter
    if not token:
        token = request.headers.get("X-API-Token") or request.headers.get("x-api-token")
    if not token:
        token = request.query_params.get("token") or request.query_params.get("api_token")

    # 3. Fallback check for Cookie
    if not token and hasattr(request, "cookies"):
        token = request.cookies.get("omnididact_token") or request.cookies.get("token") or request.cookies.get("api_token")

    if not token or not verify_token_string(token):
        logger.warning(f"Unauthorized request to {request.url.path} from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"}
        )
