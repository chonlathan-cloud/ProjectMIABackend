from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import Dict, List, Optional
import jwt
import httpx
import urllib.parse
from datetime import datetime, timedelta, timezone
from firebase_admin import auth as firebase_auth

from src.database import get_session
from src.jwt_utils import create_access_token, create_refresh_token
from src.models import Shop, ShopMember
from src.security import get_current_user
from src.config import settings


router = APIRouter(prefix="/auth", tags=["Authentication"])


class LineAuthRequest(BaseModel):
    lineUserId: str
    shopId: Optional[str] = None
    liffId: Optional[str] = None
    displayName: Optional[str] = None
    pictureUrl: Optional[str] = None


class LineAuthSelectRequest(BaseModel):
    lineUserId: str
    shopId: str


class LineBootstrapRequest(BaseModel):
    token: str


class RefreshTokenResponse(BaseModel):
    token: str


class LineFirebaseRequest(BaseModel):
    token: Optional[str] = None
    shopId: Optional[str] = None


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    max_age = settings.jwt_refresh_days * 24 * 60 * 60
    same_site = settings.cookie_samesite.lower() if settings.cookie_samesite else None
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=same_site,
        path="/",
    )


def _decode_signed_link_token(token: str) -> Dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    if payload.get("typ") != "line_login_link":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def _build_line_login_url(state: str) -> str:
    base = "https://access.line.me/oauth2/v2.1/authorize"
    params = {
        "response_type": "code",
        "client_id": settings.line_login_channel_id,
        "redirect_uri": settings.line_login_redirect_uri,
        "state": state,
        "scope": "profile openid",
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def _decode_line_access_token(token: str) -> Dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    if payload.get("provider") != "line":
        raise HTTPException(status_code=401, detail="Invalid token provider")
    return payload


async def _fetch_line_profile(code: str) -> Dict:
    token_url = "https://api.line.me/oauth2/v2.1/token"
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.line_login_redirect_uri,
        "client_id": settings.line_login_channel_id,
        "client_secret": settings.line_login_channel_secret,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(token_url, data=form)
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange LINE code")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Missing access token")

        profile_resp = await client.get(
            "https://api.line.me/v2/profile",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch LINE profile")
        return profile_resp.json()


@router.get("/me")
async def get_current_user_info(user: Dict = Depends(get_current_user)) -> Dict:
    """
    Get current authenticated user information.
    
    Returns:
        User information from Firebase token
    """
    return {
        "uid": user["uid"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
    }


@router.post("/line/bootstrap")
async def auth_line_bootstrap(
    payload: LineBootstrapRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict:
    link_payload = _decode_signed_link_token(payload.token)
    shop_id = link_payload.get("shop_id")
    if not shop_id:
        raise HTTPException(status_code=400, detail="Missing shop_id")

    shop_stmt = select(Shop).where(Shop.shop_id == shop_id)
    shop_result = await session.execute(shop_stmt)
    shop = shop_result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    state_payload = {
        "shop_id": shop_id,
        "typ": "line_login_state",
        "iss": settings.jwt_issuer,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state_token = jwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")
    login_url = _build_line_login_url(state_token)
    return {"loginUrl": login_url}


@router.post("/line/login-url")
async def auth_line_login_url() -> Dict:
    state_payload = {
        "typ": "line_login_state",
        "iss": settings.jwt_issuer,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state_token = jwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")
    login_url = _build_line_login_url(state_token)
    return {"loginUrl": login_url}


@router.post("/line")
async def auth_line_login(
    payload: LineAuthRequest,
    session: AsyncSession = Depends(get_session)
) -> Dict:
    if payload.shopId:
        member_stmt = (
            select(ShopMember, Shop)
            .join(Shop, Shop.shop_id == ShopMember.shop_id)
            .where(ShopMember.user_id == payload.lineUserId)
            .where(ShopMember.shop_id == payload.shopId)
            .where(ShopMember.auth_provider == "line")
        )
        member_result = await session.execute(member_stmt)
        member_row = member_result.first()

        if member_row:
            member, shop = member_row
            access_payload = {
                "user_id": member.user_id,
                "shop_id": member.shop_id,
                "role": member.role,
                "provider": member.auth_provider,
            }
            token = create_access_token(access_payload)
            response = JSONResponse({
                "success": True,
                "requiresSelection": False,
                "token": token,
                "shopId": shop.shop_id,
                "shopName": shop.name,
                "role": member.role,
            })
            _set_refresh_cookie(response, create_refresh_token(access_payload))
            return response

        shop_stmt = select(Shop).where(Shop.shop_id == payload.shopId)
        shop_result = await session.execute(shop_stmt)
        shop = shop_result.scalar_one_or_none()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        member = ShopMember(
            shop_id=shop.shop_id,
            user_id=payload.lineUserId,
            role="owner",
            auth_provider="line",
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)

        access_payload = {
            "user_id": member.user_id,
            "shop_id": member.shop_id,
            "role": member.role,
            "provider": member.auth_provider,
        }
        token = create_access_token(access_payload)
        response = JSONResponse({
            "success": True,
            "requiresSelection": False,
            "token": token,
            "shopId": shop.shop_id,
            "shopName": shop.name,
            "role": member.role,
        })
        _set_refresh_cookie(response, create_refresh_token(access_payload))
        return response

    statement = (
        select(ShopMember, Shop)
        .join(Shop, Shop.shop_id == ShopMember.shop_id)
        .where(ShopMember.user_id == payload.lineUserId)
        .where(ShopMember.auth_provider == "line")
    )
    result = await session.execute(statement)
    rows = result.all()

    if not rows:
        raise HTTPException(status_code=403, detail="No shop access for this LINE user")

    if len(rows) > 1:
        shops = [
            {
                "shopId": shop.shop_id,
                "shopName": shop.name,
                "role": member.role,
            }
            for member, shop in rows
        ]
        return {
            "success": True,
            "requiresSelection": True,
            "shops": shops,
        }

    member, shop = rows[0]
    access_payload = {
        "user_id": member.user_id,
        "shop_id": member.shop_id,
        "role": member.role,
        "provider": member.auth_provider,
    }
    token = create_access_token(access_payload)
    response = JSONResponse({
        "success": True,
        "requiresSelection": False,
        "token": token,
        "shopId": shop.shop_id,
        "shopName": shop.name,
        "role": member.role,
    })
    _set_refresh_cookie(response, create_refresh_token(access_payload))
    return response


@router.get("/line/callback")
async def auth_line_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        state_payload = jwt.decode(
            state,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid state: {exc}")

    if state_payload.get("typ") != "line_login_state":
        raise HTTPException(status_code=401, detail="Invalid state type")

    profile = await _fetch_line_profile(code)
    line_user_id = profile.get("userId")
    if not line_user_id:
        raise HTTPException(status_code=400, detail="Missing line user id")

    shop_id = state_payload.get("shop_id")
    if shop_id:
        member_stmt = (
            select(ShopMember)
            .where(ShopMember.shop_id == shop_id)
            .where(ShopMember.user_id == line_user_id)
            .where(ShopMember.auth_provider == "line")
        )
        member_result = await session.execute(member_stmt)
        member = member_result.scalar_one_or_none()

        if not member:
            member = ShopMember(
                shop_id=shop_id,
                user_id=line_user_id,
                role="owner",
                auth_provider="line",
            )
            session.add(member)
            await session.commit()
            await session.refresh(member)
        selected_shop_id = member.shop_id
        selected_role = member.role
    else:
        rows_stmt = (
            select(ShopMember, Shop)
            .join(Shop, Shop.shop_id == ShopMember.shop_id)
            .where(ShopMember.user_id == line_user_id)
            .where(ShopMember.auth_provider == "line")
            .order_by(ShopMember.created_at.desc())
        )
        rows_result = await session.execute(rows_stmt)
        rows = rows_result.all()
        if not rows:
            base = settings.frontend_base_url.rstrip("/")
            return RedirectResponse(url=f"{base}/line-login?error=no_shop")

        member, shop = rows[0]
        selected_shop_id = shop.shop_id
        selected_role = member.role

    access_payload = {
        "user_id": line_user_id,
        "shop_id": selected_shop_id,
        "role": selected_role,
        "provider": "line",
    }
    token = create_access_token(access_payload)

    base = settings.frontend_base_url.rstrip("/")
    redirect_url = (
        f"{base}/line-login?token={urllib.parse.quote(token)}"
        f"&shopId={urllib.parse.quote(selected_shop_id)}"
        f"&lineUserId={urllib.parse.quote(line_user_id)}"
    )
    response = RedirectResponse(url=redirect_url)
    _set_refresh_cookie(response, create_refresh_token(access_payload))
    return response


@router.post("/line/select")
async def auth_line_select(
    payload: LineAuthSelectRequest,
    session: AsyncSession = Depends(get_session)
) -> Dict:
    statement = (
        select(ShopMember, Shop)
        .join(Shop, Shop.shop_id == ShopMember.shop_id)
        .where(ShopMember.user_id == payload.lineUserId)
        .where(ShopMember.shop_id == payload.shopId)
        .where(ShopMember.auth_provider == "line")
    )
    result = await session.execute(statement)
    row = result.first()

    if not row:
        shop_stmt = select(Shop).where(Shop.shop_id == payload.shopId)
        shop_result = await session.execute(shop_stmt)
        shop = shop_result.scalar_one_or_none()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        member = ShopMember(
            shop_id=shop.shop_id,
            user_id=payload.lineUserId,
            role="owner",
            auth_provider="line",
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)

        access_payload = {
            "user_id": member.user_id,
            "shop_id": member.shop_id,
            "role": member.role,
            "provider": member.auth_provider,
        }
        token = create_access_token(access_payload)
        response = JSONResponse({
            "success": True,
            "token": token,
            "shopId": shop.shop_id,
            "shopName": shop.name,
            "role": member.role,
        })
        _set_refresh_cookie(response, create_refresh_token(access_payload))
        return response

    member, shop = row
    access_payload = {
        "user_id": member.user_id,
        "shop_id": member.shop_id,
        "role": member.role,
        "provider": member.auth_provider,
    }
    token = create_access_token(access_payload)
    response = JSONResponse({
        "success": True,
        "token": token,
        "shopId": shop.shop_id,
        "shopName": shop.name,
        "role": member.role,
    })
    _set_refresh_cookie(response, create_refresh_token(access_payload))
    return response


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_access_token(request: Request) -> JSONResponse:
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = jwt.decode(
            refresh_token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid refresh token: {exc}")

    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token type")

    access_payload = {
        "user_id": payload.get("user_id"),
        "shop_id": payload.get("shop_id"),
        "role": payload.get("role"),
        "provider": payload.get("provider"),
    }
    token = create_access_token(access_payload)
    response = JSONResponse({"token": token})
    _set_refresh_cookie(response, create_refresh_token(access_payload))
    return response


@router.post("/line/firebase")
async def auth_line_firebase(
    payload: LineFirebaseRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Dict:
    auth_header = request.headers.get("Authorization", "")
    bearer_token = ""
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()

    raw_token = payload.token or bearer_token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing line token")

    access_payload = _decode_line_access_token(raw_token)
    line_user_id = access_payload.get("user_id")
    if not line_user_id:
        raise HTTPException(status_code=401, detail="Missing line user id")

    shop_id = payload.shopId or access_payload.get("shop_id")
    if shop_id:
        member_stmt = (
            select(ShopMember)
            .where(ShopMember.user_id == line_user_id)
            .where(ShopMember.shop_id == shop_id)
            .where(ShopMember.auth_provider == "line")
        )
        member_result = await session.execute(member_stmt)
        member = member_result.scalar_one_or_none()
        if not member:
            raise HTTPException(status_code=403, detail="No shop access for this LINE user")
        role = member.role
    else:
        member_stmt = (
            select(ShopMember)
            .where(ShopMember.user_id == line_user_id)
            .where(ShopMember.auth_provider == "line")
            .order_by(ShopMember.created_at.desc())
        )
        member_result = await session.execute(member_stmt)
        member = member_result.scalars().first()
        if not member:
            raise HTTPException(status_code=403, detail="No shop access for this LINE user")
        shop_id = member.shop_id
        role = member.role

    custom_token = firebase_auth.create_custom_token(
        line_user_id,
        developer_claims={
            "shop_id": shop_id,
            "role": role,
            "provider": "line",
        },
    )

    return {
        "firebaseToken": custom_token.decode("utf-8"),
        "shopId": shop_id,
        "role": role,
    }
