from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database import get_session
from src.security import get_current_user
from src.models import Shop, StoreCreate, StoreResponse, LineCredentials, LineCredentialsResponse
from typing import Dict, List
import uuid


router = APIRouter(prefix="/stores", tags=["Stores"])


@router.get("", response_model=List[StoreResponse])
async def get_user_stores(
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> List[Shop]:
    """
    Get all stores owned by the current user.
    
    Returns:
        List of stores filtered by owner_uid
    """
    # Query stores by owner_uid
    statement = select(Shop).where(Shop.owner_uid == user["uid"])
    result = await session.execute(statement)
    stores = result.scalars().all()
    
    return stores


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store(
    store_data: StoreCreate,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Shop:
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
    
    return new_shop


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
        "lineUserId": credentials.lineUserId
    }
    
    session.add(shop)
    await session.commit()
    
    return LineCredentialsResponse(
        success=True,
        message="LINE credentials saved successfully"
    )
