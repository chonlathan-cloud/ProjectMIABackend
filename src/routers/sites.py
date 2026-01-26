from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database import get_session
from src.security import get_current_user, get_auth_context
from src.models import ShopSite, Shop, SiteConfigRequest, SiteConfigResponse, ShopPublication, ShopMember
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid


router = APIRouter(prefix="/sites", tags=["Website Builder"])


class PublishRequest(BaseModel):
    storeId: str


async def _ensure_shop_access(
    session: AsyncSession,
    store_id: str,
    auth_ctx: Dict[str, Any],
) -> Shop:
    shop_statement = select(Shop).where(Shop.shop_id == store_id)
    shop_result = await session.execute(shop_statement)
    shop = shop_result.scalar_one_or_none()

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found"
        )

    if auth_ctx.get("auth") == "firebase":
        if shop.owner_uid == auth_ctx.get("uid"):
            return shop
        member_stmt = (
            select(ShopMember)
            .where(ShopMember.shop_id == store_id)
            .where(ShopMember.user_id == auth_ctx.get("uid"))
            .where(ShopMember.auth_provider == "firebase")
        )
        member_result = await session.execute(member_stmt)
        member = member_result.scalar_one_or_none()
        if not member or member.role not in {"owner", "staff"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to modify this store"
            )
        return shop

    # LINE token context
    if auth_ctx.get("shop_id") and auth_ctx.get("shop_id") != store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this store"
        )

    member_stmt = (
        select(ShopMember)
        .where(ShopMember.shop_id == store_id)
        .where(ShopMember.user_id == auth_ctx.get("user_id"))
        .where(ShopMember.auth_provider == "line")
    )
    member_result = await session.execute(member_stmt)
    member = member_result.scalar_one_or_none()
    if not member or member.role not in {"owner", "staff"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this store"
        )
    return shop


@router.get("", response_model=Optional[SiteConfigResponse])
async def get_site_config(
    storeId: str = Query(..., description="Store ID"),
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Optional[ShopSite]:
    """
    Get the latest site configuration for a store.
    
    Args:
        storeId: Store ID to get site config for
        
    Returns:
        Site configuration or None if not found
        
    Raises:
        403: User doesn't own this store
    """
    # Verify shop ownership
    shop_statement = select(Shop).where(Shop.shop_id == storeId)
    shop_result = await session.execute(shop_statement)
    shop = shop_result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found"
        )
    
    if shop.owner_uid != user["uid"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this store"
        )
    
    # Get latest site config
    statement = (
        select(ShopSite)
        .where(ShopSite.shop_id == storeId)
        .order_by(ShopSite.updated_at.desc())
    )
    result = await session.execute(statement)
    site = result.scalar_one_or_none()
    
    return site


@router.put("/draft", response_model=SiteConfigResponse)
async def update_site_draft(
    site_data: SiteConfigRequest,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> ShopSite:
    """
    Update or create site configuration draft.
    
    Args:
        site_data: Complete site configuration
        
    Returns:
        Updated site configuration
        
    Raises:
        403: User doesn't own this store
    """
    # Verify shop ownership
    shop_statement = select(Shop).where(Shop.shop_id == site_data.storeId)
    shop_result = await session.execute(shop_statement)
    shop = shop_result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found"
        )
    
    if shop.owner_uid != user["uid"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this store"
        )
    
    # Check if site exists
    statement = select(ShopSite).where(ShopSite.shop_id == site_data.storeId)
    result = await session.execute(statement)
    existing_site = result.scalar_one_or_none()
    
    if existing_site:
        # Update existing site
        existing_site.config_json = site_data.config
        existing_site.updated_at = datetime.utcnow()
        session.add(existing_site)
        await session.commit()
        await session.refresh(existing_site)
        return existing_site
    else:
        # Create new site
        new_site = ShopSite(
            site_id=str(uuid.uuid4()),
            shop_id=site_data.storeId,
            config_json=site_data.config,
            status="draft"
        )
        session.add(new_site)
        await session.commit()
        await session.refresh(new_site)
        return new_site


@router.get("/publish-status")
async def get_publish_status(
    storeId: str = Query(..., description="Store ID"),
    auth_ctx: Dict[str, Any] = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    await _ensure_shop_access(session, storeId, auth_ctx)

    statement = select(ShopPublication).where(ShopPublication.shop_id == storeId)
    result = await session.execute(statement)
    publication = result.scalar_one_or_none()
    published = bool(publication and publication.is_published)
    published_at = publication.published_at.isoformat().replace("+00:00", "Z") if publication and publication.published_at else None

    return {
        "success": True,
        "shopId": storeId,
        "published": published,
        "publishedAt": published_at,
    }


@router.post("/publish")
async def publish_site(
    payload: PublishRequest,
    auth_ctx: Dict[str, Any] = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    store_id = payload.storeId
    await _ensure_shop_access(session, store_id, auth_ctx)

    now = datetime.now(timezone.utc)
    statement = select(ShopPublication).where(ShopPublication.shop_id == store_id)
    result = await session.execute(statement)
    publication = result.scalar_one_or_none()

    if publication:
        publication.is_published = True
        publication.published_at = now
        publication.updated_at = now
        session.add(publication)
    else:
        publication = ShopPublication(
            shop_id=store_id,
            is_published=True,
            published_at=now,
            updated_at=now,
        )
        session.add(publication)

    await session.commit()
    await session.refresh(publication)

    return {
        "success": True,
        "shopId": store_id,
        "published": True,
        "publishedAt": publication.published_at.isoformat().replace("+00:00", "Z"),
    }
