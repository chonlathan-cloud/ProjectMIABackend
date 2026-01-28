from typing import Dict, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models import Shop, ShopMember


async def user_can_access_shop(
    session: AsyncSession,
    shop: Shop,
    user: Dict,
    roles: Optional[Iterable[str]] = None,
) -> bool:
    if not shop or not user:
        return False

    if shop.owner_uid == user.get("uid"):
        return True

    provider = user.get("provider")
    if provider != "line":
        return False

    member_stmt = (
        select(ShopMember)
        .where(ShopMember.shop_id == shop.shop_id)
        .where(ShopMember.user_id == user.get("uid"))
        .where(ShopMember.auth_provider == "line")
    )
    member_result = await session.execute(member_stmt)
    member = member_result.scalar_one_or_none()
    if not member:
        return False

    if roles:
        return member.role in set(roles)

    return True
