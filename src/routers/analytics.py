from fastapi import APIRouter, Depends, Query
from typing import Dict
from src.security import get_current_user

router = APIRouter(tags=["Analytics"])

@router.get("/dashboard/recent-messages")
async def get_recent_messages(user: Dict = Depends(get_current_user)):
    # Logic: query chat_events ล่าสุด 5-10 รายการของร้านที่ user เป็นเจ้าของ
    # ตอนนี้ return empty list ไปก่อนเพื่อให้ FE ไม่ error
    return []

@router.get("/analytics")
async def get_analytics(
    storeId: str = Query(...),
    period: int = 30,
    user: Dict = Depends(get_current_user)
):
    # Logic: คำนวณ stats ต่างๆ
    return {
        "success": True,
        "message": "ok",
        "data": {
            "period": period,
            "dailyMessages": {},
            "eventTypeStats": [],
            "broadcastStats": [],
            "followerTrend": {},
            "summary": {
                "totalMessages": 0,
                "totalBroadcasts": 0,
                "avgClickRate": "0%"
            }
        }
    }