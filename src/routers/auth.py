from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import Dict, List, Optional
import jwt
import httpx
import urllib.parse
from datetime import datetime, timedelta

from src.database import get_session
from src.jwt_utils import create_access_token
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
        "exp": int((datetime.utcnow() + timedelta(minutes=10)).timestamp()),
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
            token = create_access_token(
                {
                    "user_id": member.user_id,
                    "shop_id": member.shop_id,
                    "role": member.role,
                    "provider": member.auth_provider,
                }
            )
            return {
                "success": True,
                "requiresSelection": False,
                "token": token,
                "shopId": shop.shop_id,
                "shopName": shop.name,
                "role": member.role,
            }

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

        token = create_access_token(
            {
                "user_id": member.user_id,
                "shop_id": member.shop_id,
                "role": member.role,
                "provider": member.auth_provider,
            }
        )
        return {
            "success": True,
            "requiresSelection": False,
            "token": token,
            "shopId": shop.shop_id,
            "shopName": shop.name,
            "role": member.role,
        }

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
    token = create_access_token(
        {
            "user_id": member.user_id,
            "shop_id": member.shop_id,
            "role": member.role,
            "provider": member.auth_provider,
        }
    )
    return {
        "success": True,
        "requiresSelection": False,
        "token": token,
        "shopId": shop.shop_id,
        "shopName": shop.name,
        "role": member.role,
    }


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

    shop_id = state_payload.get("shop_id")
    if not shop_id:
        raise HTTPException(status_code=400, detail="Missing shop_id")

    profile = await _fetch_line_profile(code)
    line_user_id = profile.get("userId")
    if not line_user_id:
        raise HTTPException(status_code=400, detail="Missing line user id")

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

    token = create_access_token(
        {
            "user_id": member.user_id,
            "shop_id": member.shop_id,
            "role": member.role,
            "provider": member.auth_provider,
        }
    )

    base = settings.frontend_base_url.rstrip("/")
    redirect_url = (
        f"{base}/line-login?token={urllib.parse.quote(token)}"
        f"&shopId={urllib.parse.quote(shop_id)}"
        f"&lineUserId={urllib.parse.quote(line_user_id)}"
    )
    return RedirectResponse(url=redirect_url)


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

        token = create_access_token(
            {
                "user_id": member.user_id,
                "shop_id": member.shop_id,
                "role": member.role,
                "provider": member.auth_provider,
            }
        )
        return {
            "success": True,
            "token": token,
            "shopId": shop.shop_id,
            "shopName": shop.name,
            "role": member.role,
        }

    member, shop = row
    token = create_access_token(
        {
            "user_id": member.user_id,
            "shop_id": member.shop_id,
            "role": member.role,
            "provider": member.auth_provider,
        }
    )
    return {
        "success": True,
        "token": token,
        "shopId": shop.shop_id,
        "shopName": shop.name,
        "role": member.role,
    }
