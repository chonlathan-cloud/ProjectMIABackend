from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database import get_session
from src.security import get_current_user
from src.models import Shop, BroadcastPrompt, BroadcastResponse, KnowledgeUploadResponse
from src.services.ai_service import ai_service
from src.services.storage_service import storage_service
from typing import Dict


router = APIRouter(tags=["AI & MCP"])


@router.post("/mcp/line/broadcast/ai", response_model=BroadcastResponse)
async def generate_broadcast_message(
    prompt_data: BroadcastPrompt,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> BroadcastResponse:
    """
    Generate LINE Flex Message from natural language prompt using AI.
    
    Args:
        prompt_data: User's marketing prompt and store ID
        
    Returns:
        Generated Flex Message JSON
        
    Raises:
        403: User doesn't own this store
        404: Store not found
    """
    # Verify shop ownership
    shop_statement = select(Shop).where(Shop.shop_id == prompt_data.storeId)
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
    
    # TODO: Fetch products from database for context
    # For now, using mock products
    products = [
        {"name": "Coffee", "price": 50},
        {"name": "Orange Juice", "price": 40},
        {"name": "Sandwich", "price": 60}
    ]
    
    try:
        # Generate Flex Message using AI
        flex_message = await ai_service.generate_line_flex_message(
            user_prompt=prompt_data.content,
            products=products
        )
        
        return BroadcastResponse(
            flexMessage=flex_message,
            preview="AI-generated Flex Message"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI generation failed: {str(e)}"
        )


@router.post("/api/knowledge/upload", response_model=KnowledgeUploadResponse)
async def upload_knowledge_file(
    file: UploadFile = File(...),
    storeId: str = None,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> KnowledgeUploadResponse:
    """
    Upload file for RAG (Retrieval-Augmented Generation) knowledge base.
    
    Supports PDF and image files. Extracts text, generates embeddings,
    and stores in the knowledge base.
    
    Args:
        file: Uploaded file (PDF or image)
        storeId: Store ID to associate knowledge with
        
    Returns:
        Upload success response with file URL
        
    Raises:
        400: Invalid file type
        403: User doesn't own this store
    """
    # Verify shop ownership if storeId provided
    if storeId:
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
    
    # Validate file type
    allowed_types = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/jpg"
    ]
    
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Upload to GCS
        blob_name, public_url = await storage_service.upload_file(
            file_content=file_content,
            filename=file.filename,
            content_type=file.content_type
        )
        
        # Extract text from document
        extracted_text = await ai_service.extract_text_from_document(
            file_content=file_content,
            mime_type=file.content_type
        )
        
        # Generate embeddings
        embeddings = await ai_service.generate_embeddings(extracted_text)
        
        # TODO: Store embeddings in database (shop_knowledge table)
        # For now, just return success
        
        return KnowledgeUploadResponse(
            success=True,
            file_url=public_url,
            message=f"File uploaded and processed successfully. Extracted {len(extracted_text)} characters."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File processing failed: {str(e)}"
        )
