# Scalability and Architecture Considerations

This document addresses scalability challenges and architectural decisions for the URL Shortener service, focusing on high-traffic scenarios, multi-instance deployments, and performance optimization.

---

## Table of Contents

1. [Short Code Pool System (High-Concurrency Code Assignment)](#short-code-pool)
2. [Heavy Logging Without Impacting Main Service](#heavy-logging)
3. [Multi-Instance Deployment Considerations](#multi-instance)
4. [Handling High Traffic Campaigns](#high-traffic)
5. [Architecture Diagrams](#architecture-diagrams)

---

## 1. Short Code Pool System (High-Concurrency Code Assignment) {#short-code-pool}

### Problem Statement

Traditional on-demand ID generation creates database contention when multiple instances generate codes simultaneously. Each request must insert a record, get an auto-incrementing ID, and encode it - creating a bottleneck.

### Solution: Pre-Allocated Short Code Pool

Pre-allocated short codes in memory eliminate database contention for code generation.

#### Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Service Instance 1                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Short Code Pool (1000 codes)            │   │
│  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ...       │   │
│  │  │0001│ │0002│ │0003│ │0004│ │0005│ ...       │   │
│  │  └────┘ └────┘ └────┘ └────┘ └────┘ ...       │   │
│  └──────────────────────────────────────────────────┘   │
│              │                                            │
│              │ When pool empty                            │
│              ▼                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Batch Reservation: Reserve next ID range        │   │
│  │  - Lock table (sequential)                       │   │
│  │  - Find max end_id                               │   │
│  │  - Reserve IDs 11-20 (batch_size=10)            │   │
│  │  - Generate codes in memory                      │   │
│  │  - Add to pool                                   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              Service Instance 2                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Short Code Pool (1000 codes)            │   │
│  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ...       │   │
│  │  │0021│ │0022│ │0023│ │0024│ │0025│ ...       │   │
│  │  └────┘ └────┘ └────┘ └────┘ └────┘ ...       │   │
│  └──────────────────────────────────────────────────┘   │
│              │                                            │
│              │ Independent pool (no contention)           │
│              ▼                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Batch Reservation: Reserve next ID range        │   │
│  │  - Lock table (waits for Instance 1)            │   │
│  │  - Finds max end_id = 20                         │   │
│  │  - Reserves IDs 21-30                            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

#### How It Works

1. **Service Registration (Startup)**: Service reserves an available ID (1-100) from `registered_services` table
2. **Pool Initialization**: Reserves first batch of IDs via `url_batch_reserve`, generates fixed 7-character codes in memory (`0000000`, `0000001`, etc.), stores in pool
3. **Code Assignment**: Randomly selects code from pool (O(1)), decodes to get ID, creates `ShortURL` record on-demand, returns code
4. **Auto-Refill**: When pool empty, locks table, finds max `end_id`, reserves next batch sequentially, generates codes, adds to pool

#### Key Features

- **Fixed 7-character codes**: All codes same length (`0000000` to `zzzzzzz`)
- **Random selection**: Unpredictable code assignment
- **On-demand creation**: `ShortURL` records created only when codes are used
- **Sequential batch reservation**: Table locking ensures no overlapping ID ranges
- **Service tracking**: Each batch records which service reserved it

#### Configuration

```bash
SHORT_CODE_POOL_SIZE=1000        # Codes in memory per instance
SHORT_CODE_BATCH_SIZE=10         # IDs per batch reservation
SHORT_CODE_LENGTH=7              # Fixed code length
MAX_SERVICES=100                 # Maximum concurrent instances
```

#### Performance Benefits

- Zero database contention for code assignment
- Sub-millisecond assignment (pure memory operation)
- Scalable: Each instance has independent pool
- No conflicts: Sequential batch reservation prevents ID collisions

---

## 2. Heavy Logging Without Impacting Main Service {#heavy-logging}

### Problem Statement

Synchronous logging slows down redirects, creates database write bottlenecks, and impacts user experience.

### Solution: Background Tasks

FastAPI Background Tasks offload logging operations, ensuring redirects happen immediately while logging occurs asynchronously.

#### Architecture

```
GET /{short_code} Request Flow:

1. Request arrives
   │
   ├─→ Validate short_code
   ├─→ Query database for original_url (indexed lookup)
   │
   ├─→ Return HTTP 302 Redirect (immediate response)
   │
   └─→ Background Tasks (non-blocking):
       ├─→ VisitLoggerService.log_visit()
       │   ├─→ Creates own database session
       │   ├─→ Inserts VisitLog record
       │   └─→ Commits and closes session
       │
       └─→ VisitCountService.increment_visit_count()
           ├─→ Creates own database session
           ├─→ Atomic UPDATE: visit_count = visit_count + 1
           └─→ Commits and closes session
```

#### Implementation Details

- **Independent sessions**: Each background task creates its own database session
- **Error handling**: Logs errors but doesn't crash the application
- **Visit logging**: Detailed logs in `visit_logs` table (IP, timestamp, user agent)
- **Visit count**: Denormalized count in `short_urls` table, atomic increment

#### Benefits

- Non-blocking: Redirects happen immediately (<50ms)
- Scalable: Logging doesn't impact main service performance
- Fault tolerant: Logging failures don't affect redirects
- Future-proof: Can move to message queue (Redis Queue, RabbitMQ) later

#### Future Enhancement: Message Queue

```
Current: Request → Redirect → Background Task → Database
Future:  Request → Redirect → Queue → Worker Process → Database
```

**Benefits**: Isolates logging completely, scales workers independently, better fault tolerance, handles millions of visits/day

---

## 3. Multi-Instance Deployment Considerations {#multi-instance}

### Problem Statement

Multiple service instances must run concurrently without ID collisions, requiring coordination for batch reservations.

### Solution: Service Registry + Batch Reservation

**Service Registry** assigns unique IDs to each instance. **Batch Reservation** ensures sequential, non-overlapping ID ranges.

#### Service Registry

**Process:**
```
1. Service starts → ServiceRegistry.register_service()
2. Query registered_services WHERE reserved=False
3. Lock row with FOR UPDATE (atomic)
4. Set reserved=True, return service ID (1-100)
5. Use service ID for all batch reservations
```

**Table:** `registered_services` (id, service_name, reserved, registered_at, last_heartbeat)

#### Batch Reservation System

**Process:**
```
1. Service needs to refill pool
2. Database adapter locks table (SQLite: SELECT ... FOR UPDATE, PostgreSQL: LOCK TABLE)
3. Query: SELECT MAX(end_id) FROM url_batch_reserve (while holding lock)
4. Calculate: start_id = max_end_id + 1, end_id = start_id + batch_size - 1
5. Insert reservation record (start_id, end_id, reserver=service_id)
6. Commit (releases lock)
7. Generate codes from reserved ID range
```

**Table:** `url_batch_reserve` (id, start_id, end_id, reserver, reserved_at)

**Example:**
```
Instance 1 (service_id=1): IDs 1-10, 11-20 (refill)
Instance 2 (service_id=2): IDs 21-30, 31-40 (refill)
No overlapping ranges!
```

#### Database Abstraction for Locking

- **SQLiteAdapter**: Uses `SELECT ... FOR UPDATE` on all rows
- **PostgreSQLAdapter** (future): Uses `LOCK TABLE ... IN EXCLUSIVE MODE`
- Allows SQLite by default, easy switching to PostgreSQL

#### Multi-Instance Architecture

```
                    ┌─────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌─────▼─────┐      ┌────▼────┐
   │Instance 1│       │Instance 2│      │Instance N│
   │Service ID:1│      │Service ID:2│     │Service ID:N│
   │Pool: 1000│       │Pool: 1000│      │Pool: 1000│
   └────┬────┘       └─────┬─────┘      └────┬────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌─────▼─────┐      ┌────▼────┐
   │ SQLite  │       │registered│      │url_batch│
   │Database │       │_services │      │_reserve │
   └─────────┘       └──────────┘      └─────────┘
```

**Key Points:**
- Each instance has independent code pool
- Shared database for coordination
- Sequential batch reservation prevents conflicts
- Service registry tracks active instances

---

## 4. Handling High Traffic Campaigns {#high-traffic}

### Current Capacity

**Single Instance (SQLite):**
- Shorten: 50-200 RPS
- Redirect: 500-1000 RPS
- Stats: 200-500 RPS

**Multi-Instance (5 instances):**
- Shorten: 250-1000 RPS
- Redirect: 2,500-5,000 RPS
- Stats: 1,000-2,500 RPS

### Scaling Strategy

#### Level 1: Add Caching (10x Capacity)

**Redis Cache for Redirects:**
- Cache hot URLs (90%+ hit rate)
- Sub-millisecond response times
- Reduces database load by 90%

```
GET /{code}
├── Check Redis cache
│   ├── Hit: Return (<1ms)
│   └── Miss: Query DB → Cache → Return (~10ms)
```

**Expected Impact:** Redirect capacity 5,000-10,000 RPS (single instance)

#### Level 2: Multiple Instances + Load Balancer

- Load balancer distributes requests
- Multiple FastAPI instances (5-10)
- Shared Redis cache
- Shared database

**Capacity:** 25,000-50,000 RPS

#### Level 3: Message Queue for Logging

- Redis Queue or RabbitMQ
- Worker processes consume from queue
- Isolated from main service

**Benefits:** Main service unaffected, handles millions of visits/day, better fault tolerance

#### Level 4: Database Scaling

- PostgreSQL primary (writes)
- Read replicas (reads)
- Connection pooling (PgBouncer)

**Capacity:** 100,000+ RPS

---

## 5. Architecture Diagrams {#architecture-diagrams}

### Current Architecture (Single Instance)

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTP Request
       ▼
┌─────────────────────────────────┐
│      FastAPI Application        │
│  ┌───────────────────────────┐   │
│  │   API Endpoints          │   │
│  │  - POST /shorten         │   │
│  │  - GET /{short_code}     │   │
│  │  - GET /stats/{code}     │   │
│  └───────────┬──────────────┘   │
│              │                   │
│  ┌───────────▼──────────────┐   │
│  │   Service Layer          │   │
│  │  - URLShorteningService   │   │
│  │  - ShortCodePool         │   │
│  │  - RedirectService       │   │
│  │  - StatsService          │   │
│  └───────────┬──────────────┘   │
│              │                   │
│  ┌───────────▼──────────────┐   │
│  │   Database Adapter       │   │
│  │  - SQLiteAdapter        │   │
│  └───────────┬──────────────┘   │
│              │                   │
│  ┌───────────▼──────────────┐   │
│  │   Database Layer         │   │
│  │  - SQLModel Models       │   │
│  │  - Async Session         │   │
│  └──────────────────────────┘   │
│                                  │
│  ┌───────────────────────────┐   │
│  │   Background Tasks        │   │
│  │  - VisitLoggerService    │   │
│  │  - VisitCountService     │   │
│  └──────────────────────────┘   │
└───────────┬─────────────────────┘
            │
    ┌───────┴────────┐
    │                │
    ▼                ▼
┌─────────┐    ┌──────────┐
│ SQLite  │    │Background│
│ Database│    │  Tasks   │
│(file.db)│    └──────────┘
└─────────┘
```

### Multi-Instance Architecture

```
                    ┌─────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌─────▼─────┐      ┌────▼────┐
   │Instance 1│       │Instance 2│      │Instance N│
   │Service ID:1│      │Service ID:2│     │Service ID:N│
   │Pool: 1000│       │Pool: 1000│      │Pool: 1000│
   └────┬────┘       └─────┬─────┘      └────┬────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌─────▼─────┐      ┌────▼────┐
   │ SQLite  │       │registered│      │url_batch│
   │Database │       │_services │      │_reserve │
   └─────────┘       └──────────┘      └─────────┘
```

### Production Architecture (Scaled)

```
                    ┌─────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌─────▼─────┐      ┌────▼────┐
   │Instance 1│       │Instance 2│      │Instance N│
   └────┬────┘       └─────┬─────┘      └────┬────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌─────▼─────┐      ┌────▼────┐
   │  Redis  │       │PostgreSQL │      │  Queue  │
   │  Cache  │       │  Primary  │      │ Workers │
   └─────────┘       └─────┬─────┘      └─────────┘
                           │
                     ┌──────▼──────┐
                     │PostgreSQL   │
                     │  Replicas   │
                     └─────────────┘
```

### Data Flow: URL Shortening

```
1. POST /shorten
   │
   ├─→ Validate URL
   ├─→ Check if URL already exists (deduplication)
   │
   ├─→ Get code from ShortCodePool
   │   ├─→ Random selection from pool (O(1))
   │   └─→ If pool empty: wait for refill
   │
   ├─→ Create ShortURL record (on-demand)
   │   ├─→ Decode code to get ID
   │   ├─→ Insert ShortURL with that ID
   │   └─→ Commit
   │
   └─→ Return short_code and short_url
```

### Data Flow: URL Redirection

```
1. GET /{short_code}
   │
   ├─→ Validate short_code format
   ├─→ Query database for original_url
   │   └─→ Indexed lookup by short_code
   │
   ├─→ Return HTTP 302 Redirect (immediate)
   │
   └─→ Background Tasks (non-blocking):
       ├─→ VisitLoggerService.log_visit()
       │   └─→ Insert VisitLog record
       │
       └─→ VisitCountService.increment_visit_count()
           └─→ Atomic UPDATE visit_count
```

---

## Configuration and Monitoring

### Configuration

```bash
SHORT_CODE_POOL_SIZE=1000        # Codes in memory per instance
SHORT_CODE_BATCH_SIZE=10         # IDs per batch reservation
SHORT_CODE_LENGTH=7              # Fixed code length
MAX_SERVICES=100                 # Maximum concurrent instances
```

**Database:** SQLite (default) or PostgreSQL (via adapter)

### Monitoring

**Key Metrics:**
- Request rate (RPS) per endpoint
- Response times (P50, P95, P99)
- Error rate
- Pool size and refill frequency
- Database connection pool usage
- Cache hit rate (when implemented)
- Service registry: active instances

**Health Checks:** `GET /health` for service health and database connectivity

---

## Best Practices

1. **Start with SQLite**: Perfect for development and single-instance testing
2. **Monitor Pool**: Watch refill frequency (indicates load)
3. **Add Caching**: First optimization for redirects (10x capacity)
4. **Scale Horizontally**: Add instances before optimizing single instance
5. **Use Message Queue**: For high-volume logging (millions/day)
6. **Database Replicas**: For read-heavy workloads
7. **Service Registry**: Monitor active instances and cleanup on shutdown

---

**For implementation details, see [README.md](./README.md)**
