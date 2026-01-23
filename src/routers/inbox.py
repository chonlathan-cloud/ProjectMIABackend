from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import desc
from src.database import get_session
from src.security import get_current_user
from src.models import (
    Customer, ChatEvent, Shop,
    CustomerResponse, ChatEventResponse, MessageSendRequest
)
from src.services.pubsub_service import pubsub_service
from typing import Any, Dict, List
from datetime import datetime
from linebot import LineBotApi
from linebot.models import TextSendMessage
import json


router = APIRouter(prefix="/inbox", tags=["Inbox & Messaging"])


@router.get("/customers", response_model=List[CustomerResponse])
async def get_customers(
    storeId: str = Query(..., description="Store ID"),
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> List[Dict]:
    """
    Get all customers for a store with their last message.
    
    Args:
        storeId: Store ID to get customers for
        
    Returns:
        List of customers with last message preview
        
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
    
    # Get customers
    customer_statement = (
        select(Customer)
        .where(Customer.shop_id == storeId)
        .order_by(desc(Customer.last_active_at))
    )
    customer_result = await session.execute(customer_statement)
    customers = customer_result.scalars().all()
    
    # Enrich with last message
    customer_list = []
    for customer in customers:
        # Get last message
        message_statement = (
            select(ChatEvent)
            .where(ChatEvent.customer_id == customer.customer_id)
            .order_by(desc(ChatEvent.timestamp))
            .limit(1)
        )
        message_result = await session.execute(message_statement)
        last_message = message_result.scalar_one_or_none()
        
        customer_dict = {
            "customer_id": customer.customer_id,
            "shop_id": customer.shop_id,
            "line_user_id": customer.line_user_id,
            "display_name": customer.display_name,
            "picture_url": customer.picture_url,
            "last_active_at": customer.last_active_at,
            "last_message": last_message.content if last_message else None
        }
        customer_list.append(customer_dict)
    
    return customer_list


@router.get("/history/{customer_id}", response_model=List[ChatEventResponse])
async def get_chat_history(
    customer_id: str,
    storeId: str = Query(..., description="Store ID"),
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> List[ChatEvent]:
    """
    Get full chat history for a customer.
    
    Args:
        customer_id: Customer ID
        storeId: Store ID
        
    Returns:
        List of chat messages ordered by timestamp
        
    Raises:
        403: User doesn't own this store
        404: Customer not found
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
    
    # Verify customer belongs to this shop
    customer_statement = select(Customer).where(
        Customer.customer_id == customer_id,
        Customer.shop_id == storeId
    )
    customer_result = await session.execute(customer_statement)
    customer = customer_result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Get chat history
    statement = (
        select(ChatEvent)
        .where(
            ChatEvent.customer_id == customer_id,
            ChatEvent.shop_id == storeId
        )
        .order_by(ChatEvent.timestamp.asc())
    )
    result = await session.execute(statement)
    messages = result.scalars().all()
    
    return messages


@router.get("/stream/{customer_id}")
async def stream_messages(
    customer_id: str,
    storeId: str = Query(..., description="Store ID"),
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Server-Sent Events (SSE) stream for real-time message updates.
    
    Args:
        customer_id: Customer ID to stream messages for
        storeId: Store ID
        
    Returns:
        SSE stream of new messages
        
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
    
    async def event_generator():
        """Generate SSE events from Pub/Sub."""
        try:
            async for message in pubsub_service.stream_messages(storeId, customer_id):
                # Format as SSE
                yield f"data: {json.dumps(message)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering in nginx
        }
    )


@router.post("/send/{customer_id}")
async def send_message(
    customer_id: str,
    message_data: MessageSendRequest,
    storeId: str = Query(..., description="Store ID"),
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Dict:
    """
    Send a message to a customer via LINE.
    
    Args:
        customer_id: Customer ID to send message to
        message_data: Message content
        storeId: Store ID
        
    Returns:
        Success response
        
    Raises:
        403: User doesn't own this store
        404: Customer or LINE credentials not found
    """
    # Verify shop ownership and get LINE credentials
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
    
    if not shop.line_config or not shop.line_config.get("channelAccessToken"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LINE credentials not configured for this store"
        )
    
    # Get customer
    customer_statement = select(Customer).where(
        Customer.customer_id == customer_id,
        Customer.shop_id == storeId
    )
    customer_result = await session.execute(customer_statement)
    customer = customer_result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Send message via LINE Bot SDK
    try:
        line_bot_api = LineBotApi(shop.line_config["channelAccessToken"])
        line_bot_api.push_message(
            customer.line_user_id,
            TextSendMessage(text=message_data.message)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send LINE message: {str(e)}"
        )
    
    # Save message to database
    chat_event = ChatEvent(
        shop_id=storeId,
        customer_id=customer_id,
        role="assistant",
        content=message_data.message,
        timestamp=datetime.utcnow()
    )
    
    session.add(chat_event)
    await session.commit()
    
    # Publish to Pub/Sub for real-time updates
    await pubsub_service.publish_message({
        "shop_id": storeId,
        "customer_id": customer_id,
        "role": "assistant",
        "content": message_data.message,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {
        "success": True,
        "message": "Message sent successfully"
    }
# POST /inbox/suggest
@router.post("/suggest")
async def get_inbox_suggestion(
    payload: Dict[str, str], # { storeId, userId }
    user: Dict = Depends(get_current_user)
):
    # เรียก AI Service เพื่อ generate คำตอบ
    return {
        "suggestion": "สวัสดีครับ มีอะไรให้ช่วยไหมครับ (AI Generated)"
    }

# POST /inbox/customers/{customer_id}/admin
@router.post("/customers/{customer_id}/admin")
async def update_customer_admin(
    customer_id: str,
    payload: Dict[str, Any], # { storeId, isAdmin }
    user: Dict = Depends(get_current_user)
):
    # Logic: Update customer status
    return {"success": True}