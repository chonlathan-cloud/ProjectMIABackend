from sqlmodel import SQLModel, Field, Column, JSON
from pgvector.sqlalchemy import Vector
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel
import uuid


# ============================================================================
# SQLModel Table Definitions (Database Tables)
# ============================================================================

class Shop(SQLModel, table=True):
    """Store/Shop table - represents a business owned by a user."""
    __tablename__ = "shops"
    
    shop_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    owner_uid: str = Field(index=True)  # Firebase UID of the owner
    name: str
    tier: str = Field(default="free")  # free, pro, enterprise
    line_config: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    business_profile: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    ai_settings: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ShopSite(SQLModel, table=True):
    """Website builder configurations for shops."""
    __tablename__ = "shop_sites"
    
    site_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    config_json: Dict[str, Any] = Field(sa_column=Column(JSON))  # Full site configuration
    status: str = Field(default="draft")  # draft, published
    slug: Optional[str] = Field(default=None, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ShopPublication(SQLModel, table=True):
    """Publish status for shop public website."""
    __tablename__ = "shop_publications"

    shop_id: str = Field(foreign_key="shops.shop_id", primary_key=True)
    is_published: bool = Field(default=False)
    published_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Customer(SQLModel, table=True):
    """Customer/LINE user profiles linked to shops."""
    __tablename__ = "customers"
    
    customer_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    line_user_id: str = Field(index=True)  # LINE user ID
    display_name: Optional[str] = None
    picture_url: Optional[str] = None
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatEvent(SQLModel, table=True):
    """Chat message history between customers and shops."""
    __tablename__ = "chat_events"
    
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    customer_id: str = Field(foreign_key="customers.customer_id", index=True)
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)


class OnboardingSession(SQLModel, table=True):
    """Onboarding/intake session for collecting Zone1/Zone2 data."""
    __tablename__ = "onboarding_sessions"

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    line_user_id: str = Field(index=True)
    status: str = Field(default="zone1_collecting")
    zone: int = Field(default=1)
    current_step: int = Field(default=1)
    collected_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Order(SQLModel, table=True):
    """E-commerce orders."""
    __tablename__ = "orders"
    
    order_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    customer_id: Optional[str] = Field(default=None, foreign_key="customers.customer_id")
    total_amount: float
    status: str = Field(default="pending")  # pending, paid, shipped, completed, cancelled
    payment_proof_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Product(SQLModel, table=True):
    __tablename__ = "products"
    
    product_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    
    name: str
    price: float = Field(default=0.0)
    stock: int = Field(default=0)
    is_active: bool = Field(default=True)
    
    # Custom Fields จาก Web Builder
    attributes: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # AI Search Data
    description_text: Optional[str] = None
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ShopKnowledge(SQLModel, table=True):
    __tablename__ = "shop_knowledge"
    
    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    
    type: str # 'QA', 'POLICY', 'PDF'
    content: str
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ShopMember(SQLModel, table=True):
    """Shop members for multi-user access (owner/staff)."""
    __tablename__ = "shop_members"

    member_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    user_id: str = Field(index=True)
    role: str = Field(default="staff")  # owner | staff
    auth_provider: str = Field(default="firebase")  # firebase | line
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AIActionDraft(SQLModel, table=True):
    """Draft actions awaiting user confirmation."""
    __tablename__ = "ai_action_drafts"

    draft_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    user_id: str = Field(index=True)
    action_type: str
    payload: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AIActionLog(SQLModel, table=True):
    """Audit log for AI write actions."""
    __tablename__ = "ai_action_logs"

    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shop_id: str = Field(foreign_key="shops.shop_id", index=True)
    user_id: str = Field(index=True)
    action_type: str
    status: str  # draft | confirmed | rejected | failed
    payload: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
# ============================================================================
# Pydantic Request/Response Schemas
# ============================================================================

# --- Store Schemas ---

class StoreCreate(BaseModel):
    """Request schema for creating a new store."""
    name: str


class StoreResponse(BaseModel):
    """Response schema for store information."""
    shop_id: str
    owner_uid: str
    name: str
    tier: str
    line_config: Optional[Dict[str, Any]] = None
    ai_settings: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# --- LINE Credentials Schemas ---

class LineCredentials(BaseModel):
    """Request schema for saving LINE Bot credentials."""
    channelAccessToken: str
    channelSecret: str
    lineUserId: str
    displayName: Optional[str] = None
    basicId: Optional[str] = None


class LineCredentialsResponse(BaseModel):
    """Response schema after saving LINE credentials."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


# --- AI Broadcast Schemas ---

class BroadcastPrompt(BaseModel):
    """Request schema for AI-generated broadcast messages."""
    content: str  # Natural language prompt
    storeId: str


class BroadcastResponse(BaseModel):
    """Response schema with generated Flex Message JSON."""
    flexMessage: Dict[str, Any]
    preview: str


# --- Customer & Chat Schemas ---

class CustomerResponse(BaseModel):
    """Response schema for customer information."""
    customer_id: str
    shop_id: str
    line_user_id: str
    display_name: Optional[str]
    picture_url: Optional[str]
    last_active_at: datetime
    last_message: Optional[str] = None  # Joined from chat_events
    
    class Config:
        from_attributes = True


class ChatEventResponse(BaseModel):
    """Response schema for chat messages."""
    event_id: str
    shop_id: str
    customer_id: str
    role: str
    content: str
    timestamp: datetime
    
    class Config:
        from_attributes = True


class MessageSendRequest(BaseModel):
    """Request schema for sending a message."""
    message: str


# --- Site Builder Schemas ---

class SiteConfigRequest(BaseModel):
    """Request schema for updating site configuration."""
    storeId: str
    config: Dict[str, Any]  # Full SiteConfigV2 from frontend


class SiteConfigResponse(BaseModel):
    """Response schema for site configuration."""
    site_id: str
    shop_id: str
    config_json: Dict[str, Any]
    status: str
    slug: Optional[str]
    updated_at: datetime
    
    class Config:
        from_attributes = True


# --- Order Schemas ---

class OrderCreate(BaseModel):
    """Request schema for creating an order."""
    shop_id: str
    customer_id: Optional[str] = None
    total_amount: float
    items: List[Dict[str, Any]]  # Product details


class OrderResponse(BaseModel):
    """Response schema for order information."""
    order_id: str
    shop_id: str
    customer_id: Optional[str]
    total_amount: float
    status: str
    payment_proof_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    """Request schema for updating order status."""
    status: str  # pending, paid, shipped, completed, cancelled


# --- Knowledge Upload Schema ---

class KnowledgeUploadResponse(BaseModel):
    """Response schema after uploading knowledge files."""
    success: bool
    file_url: str
    message: str


# --- LINE Image Upload Schema ---

class LineImageUploadRequest(BaseModel):
    """Request schema for uploading images to storage (from LINE tools)."""
    storeId: str
    fileName: str
    contentType: str
    dataBase64: str


class LineImageUploadResponse(BaseModel):
    """Response schema after uploading image to storage."""
    success: bool
    message: str
    data: Dict[str, Any]
