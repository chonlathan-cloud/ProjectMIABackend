from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from src.config import settings
from src.database import init_db
from src.routers import auth, stores, inbox, sites, orders, ai_mcp, public_sites, analytics
from firebase_admin.exceptions import FirebaseError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup: Initialize database
    print("🚀 Starting MIA-Core Backend...")
    db_ready = await init_db()
    if db_ready:
        print("✅ Database initialized")
    else:
        print("⚠️ Database initialization failed. Continuing startup without DB.")
    
    yield
    
    # Shutdown
    print("👋 Shutting down MIA-Core Backend...")


# Create FastAPI application
app = FastAPI(
    title="MIA-Core API",
    description="Backend API for MIA-Core with Firebase Auth, Google Cloud services, and real-time messaging",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# Exception Handlers
@app.exception_handler(FirebaseError)
async def firebase_exception_handler(request: Request, exc: FirebaseError):
    """Handle Firebase authentication errors."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "detail": "Authentication failed",
            "error": str(exc)
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error": str(exc)
        }
    )


# Health check endpoint
@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "MIA-Core Backend",
        "version": "2.1.0"
    }


# Register routers
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(stores.router, prefix=settings.api_prefix)
app.include_router(inbox.router, prefix=settings.api_prefix)
app.include_router(sites.router, prefix=settings.api_prefix)
app.include_router(analytics.router, prefix=f"{settings.api_prefix}/sites")
app.include_router(orders.router, prefix=settings.api_prefix)
app.include_router(ai_mcp.router)  # No prefix for MCP routes
app.include_router(public_sites.router, prefix=settings.api_prefix)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
