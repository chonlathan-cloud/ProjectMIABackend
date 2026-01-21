from fastapi import APIRouter, Depends
from src.security import get_current_user
from typing import Dict


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me")
async def get_current_user_info(user: Dict = Depends(get_current_user)) -> Dict:
    """
    Get current authenticated user information.
    
    Returns:
        User information from Firebase token
    """
    return {
        "uid": user["uid"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
    }
