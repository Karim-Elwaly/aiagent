from collections.abc import Callable
from secrets import compare_digest

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.schemas.domain import UserRole

oauth = OAuth()
if settings.oidc_client_id and settings.oidc_client_secret and settings.oidc_metadata_url:
    oauth.register(
        name="fleet-studio",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=settings.oidc_metadata_url,
        client_kwargs={"scope": "openid profile email"},
    )

router = APIRouter(prefix="/auth", tags=["authentication"])


def require_roles(*required: UserRole) -> Callable:
    async def check_role(request: Request) -> dict:
        if not settings.auth_required:
            return {"sub": "local-development", "roles": [role.value for role in UserRole]}
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        if not {role.value for role in required}.intersection(user.get("roles", [])):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return check_role


async def require_daemon_token(x_fleet_daemon_token: str | None = Header(default=None)) -> None:
    if not settings.daemon_token:
        raise HTTPException(status_code=503, detail="Daemon credentials are not configured.")
    if not x_fleet_daemon_token or not compare_digest(x_fleet_daemon_token, settings.daemon_token):
        raise HTTPException(status_code=401, detail="Valid daemon credentials are required.")


@router.get("/login")
async def login(request: Request):
    client = oauth.create_client("fleet-studio")
    if client is None:
        raise HTTPException(status_code=503, detail="OIDC is not configured")
    return await client.authorize_redirect(request, settings.oidc_redirect_uri)


@router.get("/me")
async def current_user(request: Request):
    user = request.session.get("user")
    if user is not None:
        return user
    if settings.auth_required:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"sub": "local-development", "name": "Local Operator", "roles": [role.value for role in UserRole]}


@router.get("/callback")
async def callback(request: Request):
    client = oauth.create_client("fleet-studio")
    if client is None:
        raise HTTPException(status_code=503, detail="OIDC is not configured")
    token = await client.authorize_access_token(request)
    claims = token.get("userinfo") or {}
    raw_roles = claims.get(settings.oidc_roles_claim, [])
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    valid_roles = {role.value for role in UserRole}
    request.session["user"] = {
        "sub": claims.get("sub", ""),
        "name": claims.get("name", ""),
        "email": claims.get("email", ""),
        "roles": [role for role in raw_roles if role in valid_roles],
    }
    return RedirectResponse(settings.frontend_origin)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "signed_out"}