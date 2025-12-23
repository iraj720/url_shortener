# 🔗 URL Shortener Service

A production-ready, scalable URL shortening service built with **FastAPI** and **SQLite** (default). Features database abstraction for easy switching to PostgreSQL, pre-allocated short code pools, and multi-instance support.

## ✨ Features

- **URL Shortening**: Fixed 7-character short codes (e.g., `0000000`)
- **URL Redirection**: Fast HTTP 302 redirects
- **Visit Statistics**: Track visit counts and detailed logs
- **Short Code Pool**: Pre-allocated in-memory codes for zero-database-contention
- **Multi-Instance Support**: Service registry and batch reservation system
- **Database Abstraction**: Easy switching between SQLite and PostgreSQL
- **Async/Await**: Fully asynchronous for high concurrency
- **Background Tasks**: Non-blocking logging and analytics
- **Rate Limiting**: IP-based protection
- **Auto-Generated Docs**: Swagger UI and ReDoc

## 🚀 Quick Start

```bash
# Start the service (auto-creates venv, installs deps, runs migrations)
./start.sh

# Or manually:
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Access:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

## 📚 API Endpoints

### POST /shorten
Create a short URL.

```bash
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

Response:
```json
{
  "short_code": "0000001",
  "short_url": "http://localhost:8000/0000001",
  "original_url": "https://example.com"
}
```

### GET /{short_code}
Redirect to original URL (HTTP 302).

### GET /stats/{short_code}
Get visit statistics.

## 🏗 Architecture

```
Client → FastAPI → Service Layer → Database Adapter → SQLite/PostgreSQL
                ↓
         Background Tasks (logging, analytics)
```

**Key Components:**
- **Short Code Pool**: In-memory pool of pre-allocated codes (1000 by default)
- **Batch Reservation**: Sequential ID reservation across instances
- **Service Registry**: Unique service IDs for multi-instance deployments
- **Database Adapter**: Abstraction layer for easy database switching

## 💾 Database

**Default: SQLite** (file-based, no setup needed)
- Database file: `./urlshortener.db`
- Perfect for development and testing

**Production: PostgreSQL** (optional)
- Switch by creating `PostgreSQLAdapter` and updating factory
- No code changes needed elsewhere

**Database Abstraction:**
- All database-specific code in adapters (`app/db/sqlite_adapter.py`)
- Rest of codebase uses `DatabaseAdapter` interface
- Easy to add new database backends

## 🧪 Testing

```bash
./test.sh          # All tests
./test.sh unit     # Unit tests
./test.sh load     # Load tests (server starts automatically)
```

## 📁 Project Structure

```
app/
├── api/           # FastAPI endpoints
├── services/      # Business logic (URL, redirect, stats, pool, registry)
├── db/            # Models, session, database adapters
├── core/          # Settings, exceptions, validators
└── middleware/    # Logging middleware
```

## ⚙️ Configuration

Environment variables (`.env`):
```bash
DATABASE_URL=sqlite+aiosqlite:///./urlshortener.db
BASE_URL=http://localhost:8000
SHORT_CODE_POOL_SIZE=1000
SHORT_CODE_BATCH_SIZE=10
SHORT_CODE_LENGTH=7
MAX_SERVICES=100
```

## 🔧 Design Decisions

- **Fixed 7-character codes**: All codes same length (`0000000` to `zzzzzzz`)
- **Short Code Pool**: Pre-allocated codes eliminate database contention
- **Batch Reservation**: Sequential ID ranges prevent conflicts across instances
- **Service Registry**: Unique IDs for each service instance
- **On-Demand Creation**: ShortURL records created when codes are used
- **Database Abstraction**: Interface pattern for easy database switching
- **Background Tasks**: Non-blocking logging and analytics

## 📈 Scalability

See [SCALABILITY.md](./SCALABILITY.md) for detailed scalability analysis.

**Current Capacity:**
- Single instance: 500-1000 RPS
- Multi-instance: Scales horizontally with service registry
- Short code pool: Zero database contention for code generation

**Scaling Path:**
1. Add Redis cache (90%+ hit rate)
2. Deploy multiple instances (load balancer)
3. Move logging to message queue
4. Database read replicas

## 📝 License

Part of a technical interview process.

---

**Built with ❤️ using FastAPI and Python**
