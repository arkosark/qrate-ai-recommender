"""
Cognito JWT verification — mirrors existing qrate-core auth middleware.
Tokens are validated against the Cognito public JWKS endpoint.
"""
import httpx
from jose import jwt, JWTError
from jose.utils import base64url_decode
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_security = HTTPBearer(auto_error=False)
_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    jwks_url = (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
        f"/{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(jwks_url)
        r.raise_for_status()
        _jwks_cache = r.json()
    return _jwks_cache


async def verify_cognito_token(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> dict:
    """
    FastAPI dependency. Returns the decoded JWT claims if valid.
    Raises HTTP 401 if token is missing or invalid.
    """
    if settings.environment in ("local", "test"):
        # Skip real JWT validation in local/test environments
        return {"sub": "local-test-user", "cognito:groups": ["diner"]}

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    token = credentials.credentials
    try:
        # Decode header to get kid
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        jwks = await _get_jwks()
        public_keys = {key["kid"]: key for key in jwks.get("keys", [])}

        if kid not in public_keys:
            raise HTTPException(status_code=401, detail="Invalid token key ID")

        claims = jwt.decode(
            token,
            public_keys[kid],
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
        )
        return claims
    except JWTError as exc:
        logger.warning("JWT verification failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def optional_auth(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> dict | None:
    """
    Optional auth — returns claims if token provided, None if anonymous.
    Used for /recommend which supports unauthenticated (anonymous) diners.
    """
    if not credentials:
        return None
    try:
        return await verify_cognito_token(credentials)
    except HTTPException:
        return None
