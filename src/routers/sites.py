from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database import get_session
from src.security import get_current_user
from src.models import ShopSite, Shop, SiteConfigRequest, SiteConfigResponse
from typing import Dict, Optional
from datetime import datetime
import uuid


router = APIRouter(prefix="/sites", tags=["Website Builder"])


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
