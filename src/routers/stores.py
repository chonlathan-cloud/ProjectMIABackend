from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from src.database import get_session
from src.security import get_current_user
from src.models import (
    Shop,
    StoreCreate,
    LineCredentials,
    LineCredentialsResponse,
    Customer,
    ChatEvent,
    Product,
)
from typing import Dict, Any
import uuid


router = APIRouter(prefix="/stores", tags=["Stores"])


def serialize_store(shop: Shop) -> Dict[str, Any]:
    line_config = shop.line_config or {}
    line_account_id = line_config.get("lineUserId") or line_config.get("botBasicId")

    return {
        "id": shop.shop_id,
        "shop_id": shop.shop_id,
        "name": shop.name,
        "tier": shop.tier,
        "lineConfig": line_config,
        "line_config": line_config,
        "lineAccountId": line_account_id,
        "aiSettings": shop.ai_settings,
        "ai_settings": shop.ai_settings,
        "createdAt": shop.created_at,
        "created_at": shop.created_at,
        "updatedAt": shop.updated_at,
        "updated_at": shop.updated_at,
    }


@router.get("")
async def get_user_stores(
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """
    Get all stores owned by the current user.
    
    Returns:
        List of stores filtered by owner_uid
    """
    # Query stores by owner_uid
    statement = select(Shop).where(Shop.owner_uid == user["uid"])
    result = await session.execute(statement)
    stores = result.scalars().all()
    payload = [serialize_store(store) for store in stores]

    return {
        "success": True,
        "data": {"stores": payload},
        "stores": payload
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_store(
    store_data: StoreCreate,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """
    Create a new store for the current user.
    
    Args:
        store_data: Store creation data (name)
        
    Returns:
        Created store information
    """
    # Create new shop
    new_shop = Shop(
        shop_id=str(uuid.uuid4()),
        owner_uid=user["uid"],
        name=store_data.name,
        tier="free"
    )
    
    session.add(new_shop)
    await session.commit()
    await session.refresh(new_shop)
    
    payload = serialize_store(new_shop)
    return {
        "success": True,
        "data": {"store": payload},
        "store": payload
    }


@router.post("/{shop_id}/line-credentials", response_model=LineCredentialsResponse)
async def save_line_credentials(
    shop_id: str,
    credentials: LineCredentials,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> LineCredentialsResponse:
    """
    Save LINE Bot credentials for a store.
    
    Args:
        shop_id: Store ID
        credentials: LINE Bot credentials
        
    Returns:
        Success response
        
    Raises:
        404: Store not found
        403: User doesn't own this store
    """
    # Get shop and verify ownership
    statement = select(Shop).where(Shop.shop_id == shop_id)
    result = await session.execute(statement)
    shop = result.scalar_one_or_none()
    
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
    
    # Update LINE config
    shop.line_config = {
        "channelAccessToken": credentials.channelAccessToken,
        "channelSecret": credentials.channelSecret,
        "lineUserId": credentials.lineUserId,
        "displayName": credentials.displayName,
        "basicId": credentials.basicId,
        "botBasicId": credentials.basicId
    }
    
    session.add(shop)
    await session.commit()
    
    return LineCredentialsResponse(
        success=True,
        message="LINE credentials saved successfully",
        data=shop.line_config,
        settings=shop.line_config
    )
@router.get("/{shop_id}/line-credentials", response_model=LineCredentialsResponse)
async def get_line_credentials(
    shop_id: str,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> LineCredentialsResponse:
    """Get LINE credentials for a specific shop."""
    
    # 1. ค้นหาร้าน
    statement = select(Shop).where(Shop.shop_id == shop_id)
    result = await session.execute(statement)
    shop = result.scalar_one_or_none()
    
    # 2. ตรวจสอบสิทธิ์ (เป็นเจ้าของร้านไหม)
    if not shop:
        raise HTTPException(status_code=404, detail="Store not found")
    
    if shop.owner_uid != user["uid"]:
        raise HTTPException(status_code=403, detail="Permission denied")

    # 3. ดึง Config ออกมา (ถ้าไม่มีให้คืนค่าว่าง)
    config = shop.line_config or {}
    
    return LineCredentialsResponse(
        success=True,
        message="Credentials loaded",
        data=config,
        settings=config
    )

# 1. GET /stores/{store_id}/ai-settings
@router.get("/{shop_id}/ai-settings")
async def get_ai_settings(
    shop_id: str,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    # check owner logic...
    statement = select(Shop).where(Shop.shop_id == shop_id)
    result = await session.execute(statement)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=404, detail="Store not found")
        
    return shop.ai_settings or {"aiEnable": False}

# 2. POST /stores/{store_id}/ai-settings
@router.post("/{shop_id}/ai-settings")
async def update_ai_settings(
    shop_id: str,
    settings: Dict[str, Any], # รับ json body { aiEnable: boolean }
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    statement = select(Shop).where(Shop.shop_id == shop_id)
    result = await session.execute(statement)
    shop = result.scalar_one_or_none()
    
    if not shop or shop.owner_uid != user["uid"]:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    # Merge or overwrite settings
    current_settings = shop.ai_settings or {}
    current_settings.update(settings)
    shop.ai_settings = current_settings
    
    session.add(shop)
    await session.commit()
    return {"success": True, "data": shop.ai_settings}

# 3. GET /stores/{store_id}/stats (ใช้ในหน้า Dashboard เล็กๆ)
@router.get("/{shop_id}/stats")
async def get_store_stats(
    shop_id: str,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    shop_stmt = select(Shop).where(Shop.shop_id == shop_id)
    shop_result = await session.execute(shop_stmt)
    shop = shop_result.scalar_one_or_none()

    if not shop:
        raise HTTPException(status_code=404, detail="Store not found")

    if shop.owner_uid != user["uid"]:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Count total customers for shop
    customer_stmt = select(func.count()).select_from(Customer).where(
        Customer.shop_id == shop_id
    )
    customer_result = await session.execute(customer_stmt)
    customer_count = customer_result.scalar_one() or 0

    # Count today's messages for shop (UTC day)
    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day)
    end_of_day = start_of_day + timedelta(days=1)

    message_stmt = select(func.count()).select_from(ChatEvent).where(
        ChatEvent.shop_id == shop_id,
        ChatEvent.timestamp >= start_of_day,
        ChatEvent.timestamp < end_of_day,
    )
    message_result = await session.execute(message_stmt)
    message_count = message_result.scalar_one() or 0

    return {
        "success": True,
        "stats": {
            "customers": customer_count,
            "messages": message_count
        }
    }


@router.get("/{shop_id}/onboarding")
async def get_onboarding_profile(
    shop_id: str,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    shop_stmt = select(Shop).where(Shop.shop_id == shop_id)
    shop_result = await session.execute(shop_stmt)
    shop = shop_result.scalar_one_or_none()

    if not shop:
        raise HTTPException(status_code=404, detail="Store not found")

    if shop.owner_uid != user["uid"]:
        raise HTTPException(status_code=403, detail="Permission denied")

    profile = shop.business_profile or {}

    product_stmt = (
        select(Product)
        .where(Product.shop_id == shop_id)
        .order_by(desc(Product.created_at))
        .limit(1)
    )
    product_result = await session.execute(product_stmt)
    product = product_result.scalar_one_or_none()

    first_product = None
    if product:
        image_urls = None
        image_url = None
        if product.attributes:
            image_urls = product.attributes.get("imageUrls")
            image_url = product.attributes.get("imageUrl")
        first_product = {
            "product_id": product.product_id,
            "name": product.name,
            "price": product.price,
            "description": product.description_text,
            "imageUrl": image_url,
            "imageUrls": image_urls,
        }

    return {
        "success": True,
        "data": {
            "shopName": shop.name,
            "businessProfile": profile,
            "firstProduct": first_product,
        },
    }
