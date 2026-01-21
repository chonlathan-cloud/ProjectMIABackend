# MIA-Core Backend (Server B)

Production-ready FastAPI backend for MIA-Core with Firebase Authentication, Google Cloud Pub/Sub, Vertex AI integration, and real-time messaging capabilities.

## 🏗️ Architecture

- **Framework:** FastAPI with async/await
- **Database:** PostgreSQL with SQLModel (async)
- **Authentication:** Firebase Admin SDK
- **Real-time:** Server-Sent Events (SSE) via Google Pub/Sub
- **AI:** Google Vertex AI (Gemini 1.5 Pro)
- **Storage:** Google Cloud Storage
- **Messaging:** LINE Bot SDK

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL database
- Google Cloud Project with enabled APIs:
  - Pub/Sub
  - Cloud Storage
  - Vertex AI
  - Firebase Admin
- LINE Bot credentials

## 🚀 Setup

### 1. Clone and Navigate

```bash
cd /Users/chonlathansongsri/Documents/company/ProjectMIA/Backend/ServerB_MiaCore
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to `.env` and update values:

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:
- `DB_URL`: PostgreSQL connection string
- `GOOGLE_CLOUD_PROJECT`: Your GCP project ID
- `GCS_BUCKET_NAME`: Your Cloud Storage bucket name
- Ensure `service-account-key.json` is in the project root

### 5. Initialize Database

Create the database schema:

```sql
-- Run this in your PostgreSQL database
CREATE DATABASE mia_core;
```

The tables will be created automatically on first run via SQLModel.

### 6. Run Development Server

```bash
uvicorn main:app --reload --port 8000
```

Server will start at: `http://localhost:8000`

## 📚 API Documentation

Once running, access:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## 🔑 API Endpoints

### Authentication
- `GET /api/auth/me` - Get current user profile

### Stores
- `GET /api/stores` - List user's stores
- `POST /api/stores` - Create new store
- `POST /api/stores/{shop_id}/line-credentials` - Save LINE credentials

### Inbox (Real-time Messaging)
- `GET /api/inbox/customers` - List customers with last message
- `GET /api/inbox/history/{customer_id}` - Get chat history
- `GET /api/inbox/stream/{customer_id}` - SSE stream for real-time updates
- `POST /api/inbox/send/{customer_id}` - Send message via LINE

### Website Builder
- `GET /api/sites` - Get site configuration
- `PUT /api/sites/draft` - Update site configuration

### Orders
- `GET /api/orders` - List orders
- `POST /api/orders` - Create order
- `PATCH /api/orders/{order_id}/status` - Update order status

### AI Features
- `POST /mcp/line/broadcast/ai` - Generate LINE Flex Message from prompt
- `POST /api/knowledge/upload` - Upload files for RAG

## 🔐 Authentication

All endpoints (except health checks) require Firebase authentication:

```bash
Authorization: Bearer <firebase_id_token>
```

## 🧪 Testing

```bash
# Test server health
curl http://localhost:8000/

# Test with authentication
curl -H "Authorization: Bearer YOUR_FIREBASE_TOKEN" \
     http://localhost:8000/api/stores
```

## 📦 Project Structure

```
ServerB_MiaCore/
├── main.py                   # FastAPI app entry point
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (not in git)
├── .env.example             # Environment template
├── service-account-key.json # Google Cloud credentials (not in git)
├── src/
│   ├── config.py            # Settings management
│   ├── database.py          # Database connection
│   ├── security.py          # Firebase auth
│   ├── models.py            # SQLModel tables & schemas
│   ├── services/
│   │   ├── ai_service.py    # Vertex AI integration
│   │   ├── pubsub_service.py # Pub/Sub messaging
│   │   └── storage_service.py # GCS uploads
│   └── routers/
│       ├── auth.py          # Auth endpoints
│       ├── stores.py        # Store management
│       ├── inbox.py         # Real-time messaging
│       ├── sites.py         # Website builder
│       ├── orders.py        # Order management
│       └── ai_mcp.py        # AI features
```

## 🚢 Deployment

### Google Cloud Run

```bash
# Build container
gcloud builds submit --tag gcr.io/YOUR_PROJECT/mia-core

# Deploy
gcloud run deploy mia-core \
  --image gcr.io/YOUR_PROJECT/mia-core \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Environment Variables in Production

Set all `.env` variables in your deployment platform's environment configuration.

## 📝 License

Proprietary - Project MIA

## 👥 Support

For issues or questions, contact the development team.
