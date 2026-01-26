from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import Dict, Any

from src.database import get_session
from src.models import ShopSite, ShopPublication


router = APIRouter(prefix="/public", tags=["Public Sites"])


@router.get("/sites/{shop_id}")
async def get_public_site(
    shop_id: str,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    publication_stmt = select(ShopPublication).where(ShopPublication.shop_id == shop_id)
    publication_result = await session.execute(publication_stmt)
    publication = publication_result.scalar_one_or_none()
    if not publication or not publication.is_published:
        return {
            "success": False,
            "message": "ร้านนี้ยังไม่เปิดให้ซื้อสินค้า",
        }

    site_stmt = (
        select(ShopSite)
        .where(ShopSite.shop_id == shop_id)
        .order_by(ShopSite.updated_at.desc())
    )
    site_result = await session.execute(site_stmt)
    site = site_result.scalar_one_or_none()
    if not site:
        return {
            "success": False,
            "message": "ร้านนี้ยังไม่เปิดให้ซื้อสินค้า",
        }

    return {
        "success": True,
        "storeId": shop_id,
        "config": site.config_json,
    }
