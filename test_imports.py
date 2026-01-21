#!/usr/bin/env python3
"""
Quick test script to verify the server can import all modules.
This doesn't require database or Google Cloud credentials.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("🧪 Testing MIA-Core Backend imports...")

try:
    print("✓ Importing config...")
    from src import config
    
    print("✓ Importing models...")
    from src import models
    
    print("✓ Importing routers...")
    from src.routers import auth, stores, inbox, sites, orders, ai_mcp
    
    print("\n✅ All imports successful!")
    print("\n📝 Next steps:")
    print("1. Configure .env file with your credentials")
    print("2. Create PostgreSQL database")
    print("3. Run: uvicorn main:app --reload")
    print("4. Access docs at: http://localhost:8000/docs")
    
except ImportError as e:
    print(f"\n❌ Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)
