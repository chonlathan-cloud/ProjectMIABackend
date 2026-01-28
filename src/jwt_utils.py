from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import jwt

from src.config import settings


def create_access_token(payload: Dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    data = {
        **payload,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_exp_minutes)).timestamp()),
    }
    return jwt.encode(data, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(payload: Dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    data = {
        **payload,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_refresh_days)).timestamp()),
        "typ": "refresh",
    }
    return jwt.encode(data, settings.jwt_secret, algorithm="HS256")
