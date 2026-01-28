from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database import get_session
from src.security import get_current_user
from src.models import Order, Shop, OrderCreate, OrderResponse, OrderStatusUpdate
from src.access import user_can_access_shop
from typing import Dict, List
from datetime import datetime
import uuid


router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=List[OrderResponse])
async def get_orders(
    storeId: str = Query(..., description="Store ID"),
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> List[Order]:
    """
    Get all orders for a store.
    
    Args:
        storeId: Store ID to get orders for
        
    Returns:
        List of orders
        
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
    
    if not await user_can_access_shop(session, shop, user, roles={"owner", "staff"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this store"
        )
    
    # Get orders
    statement = (
        select(Order)
        .where(Order.shop_id == storeId)
        .order_by(Order.created_at.desc())
    )
    result = await session.execute(statement)
    orders = result.scalars().all()
    
    return orders


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Order:
    """
    Create a new order.
    
    Args:
        order_data: Order creation data
        
    Returns:
        Created order
        
    Raises:
        403: User doesn't own this store
    """
    # Verify shop ownership
    shop_statement = select(Shop).where(Shop.shop_id == order_data.shop_id)
    shop_result = await session.execute(shop_statement)
    shop = shop_result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found"
        )
    
    if not await user_can_access_shop(session, shop, user, roles={"owner", "staff"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create orders for this store"
        )
    
    # Create order
    new_order = Order(
        order_id=str(uuid.uuid4()),
        shop_id=order_data.shop_id,
        customer_id=order_data.customer_id,
        total_amount=order_data.total_amount,
        status="pending"
    )
    
    session.add(new_order)
    await session.commit()
    await session.refresh(new_order)
    
    return new_order


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: str,
    status_update: OrderStatusUpdate,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Order:
    """
    Update order status.
    
    Args:
        order_id: Order ID to update
        status_update: New status
        
    Returns:
        Updated order
        
    Raises:
        404: Order not found
        403: User doesn't own the store
    """
    # Get order
    order_statement = select(Order).where(Order.order_id == order_id)
    order_result = await session.execute(order_statement)
    order = order_result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Verify shop ownership
    shop_statement = select(Shop).where(Shop.shop_id == order.shop_id)
    shop_result = await session.execute(shop_statement)
    shop = shop_result.scalar_one_or_none()
    
    if not shop or not await user_can_access_shop(session, shop, user, roles={"owner", "staff"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this order"
        )
    
    # Update status
    order.status = status_update.status
    order.updated_at = datetime.utcnow()
    
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    return order
