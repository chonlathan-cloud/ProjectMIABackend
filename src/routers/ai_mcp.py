from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database import get_session
from src.security import get_current_user
# ✅ เพิ่ม ShopKnowledge เข้ามาใน Import
from src.models import (
    Shop,
    BroadcastPrompt,
    BroadcastResponse,
    KnowledgeUploadResponse,
    LineImageUploadRequest,
    LineImageUploadResponse,
    Product,
    ShopKnowledge,
)
from src.services.ai_service import ai_service
from src.services.storage_service import storage_service
from typing import Dict
import uuid # ✅ เพิ่ม uuid สำหรับ gen id
import base64
from src.access import user_can_access_shop

router = APIRouter(tags=["AI & MCP"])

@router.post("/mcp/line/broadcast/ai", response_model=BroadcastResponse)
@router.post("/api/mcp/line/broadcast/ai", response_model=BroadcastResponse)
async def generate_broadcast_message(
    prompt_data: BroadcastPrompt,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> BroadcastResponse:
    # ... (ส่วนตรวจสอบสิทธิ์ Shop เหมือนเดิม ถูกต้องแล้ว) ...
    shop_statement = select(Shop).where(Shop.shop_id == prompt_data.storeId)
    shop_result = await session.execute(shop_statement)
    shop = shop_result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=404, detail="Store not found")
    if not await user_can_access_shop(session, shop, user, roles={"owner", "staff"}):
        raise HTTPException(status_code=403, detail="Permission denied")

    # ✅ ส่วนดึงสินค้าจริง (ถูกต้องแล้ว)
    product_statement = select(Product).where(Product.shop_id == prompt_data.storeId)
    product_result = await session.execute(product_statement)
    db_products = product_result.scalars().all()
    
    products_context = [
        {
            "name": p.name, 
            "price": p.price, 
            "stock": p.stock,
            "details": p.attributes 
        } 
        for p in db_products
    ]
    
    try:
        flex_message = await ai_service.generate_line_flex_message(
            user_prompt=prompt_data.content,
            products=products_context 
        )
        return BroadcastResponse(
            flexMessage=flex_message,
            preview="AI-generated Flex Message based on real inventory"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/line/upload-image", response_model=LineImageUploadResponse)
@router.post("/api/mcp/line/upload-image", response_model=LineImageUploadResponse)
async def upload_line_image(
    payload: LineImageUploadRequest,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> LineImageUploadResponse:
    # Verify shop ownership
    shop_statement = select(Shop).where(Shop.shop_id == payload.storeId)
    shop_result = await session.execute(shop_statement)
    shop = shop_result.scalar_one_or_none()

    if not shop:
        raise HTTPException(status_code=404, detail="Store not found")
    if not await user_can_access_shop(session, shop, user, roles={"owner", "staff"}):
        raise HTTPException(status_code=403, detail="Permission denied")

    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if payload.contentType not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid image type")

    try:
        file_content = base64.b64decode(payload.dataBase64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 data")

    try:
        blob_name, public_url = await storage_service.upload_file(
            file_content=file_content,
            filename=payload.fileName,
            content_type=payload.contentType,
            folder_prefix=shop.name
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )

    return LineImageUploadResponse(
        success=True,
        message="Image uploaded",
        data={
            "url": public_url,
            "blobName": blob_name
        }
    )


@router.post("/api/knowledge/upload", response_model=KnowledgeUploadResponse)
async def upload_knowledge_file(
    file: UploadFile = File(...),
    storeId: str = None,
    user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> KnowledgeUploadResponse:
    # ... (ส่วนตรวจสอบสิทธิ์ Shop เหมือนเดิม) ...
    if storeId:
        shop_statement = select(Shop).where(Shop.shop_id == storeId)
        shop_result = await session.execute(shop_statement)
        shop = shop_result.scalar_one_or_none()
        if not shop or not await user_can_access_shop(session, shop, user, roles={"owner", "staff"}):
             raise HTTPException(status_code=403, detail="Permission denied")

    # Validate file type
    allowed_types = ["application/pdf", "image/jpeg", "image/png", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    try:
        # 1. Upload & Extract (เหมือนเดิม)
        file_content = await file.read()
        blob_name, public_url = await storage_service.upload_file(
            file_content=file_content,
            filename=file.filename,
            content_type=file.content_type
        )
        
        extracted_text = await ai_service.extract_text_from_document(
            file_content=file_content,
            mime_type=file.content_type
        )
        
        # 2. Generate Embedding (เหมือนเดิม)
        embeddings = await ai_service.generate_embeddings(extracted_text)
        
        # 3. ✅ Save ลง Database (ส่วนที่เพิ่มเข้ามา)
        new_knowledge = ShopKnowledge(
            doc_id=str(uuid.uuid4()),
            shop_id=storeId,
            type="file_upload",
            content=extracted_text,  # เก็บข้อความไว้ให้ AI อ่าน
            embedding=embeddings     # เก็บ Vector ไว้ให้ AI ค้นหา
        )
        
        session.add(new_knowledge)
        await session.commit()
        
        return KnowledgeUploadResponse(
            success=True,
            file_url=public_url,
            message=f"Success! Extracted {len(extracted_text)} chars and saved to knowledge base."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}"
        )
