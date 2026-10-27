# ChangeGuard

**Construction Change Order & Project Risk Intelligence Platform**

ChangeGuard is an AI-powered vertical SaaS for construction project management, focusing on change order processing, risk detection, and evidence-based decision making.

## Architecture

Modular monolith built with:
- **FastAPI** - Async REST API
- **SQLAlchemy 2.0** - Async ORM with PostgreSQL
- **Pydantic v2** - Data validation
- **Alembic** - Database migrations
- **Celery + Redis** - Background job processing
- **pgvector** - Vector search for RAG
- **MinIO** - S3-compatible object storage
- **OpenTelemetry** - Observability

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ (for local development)

### Running with Docker Compose

```bash
# Clone the repository
git clone <repository-url>
cd ChangeGuard

# Copy environment file
cp .env.example .env

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

Services will be available at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
- **Frontend**: http://localhost:3000 (placeholder)

### Running Tests

```bash
# Run tests in the backend container
docker-compose exec api pytest

# Or run locally with test database
cd backend
cp .env.example .env.test
# Edit .env.test to use test database
pytest -v
```

### Local Development

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy and configure environment
cp ../.env.example .env
# Edit .env with your settings

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload

# Start Celery worker (in another terminal)
celery -A app.core.celery_app worker --loglevel=info
```

## Project Structure

```
ChangeGuard/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── core/           # Config, security, logging, database
│   │   ├── api/            # API routes and endpoints
│   │   ├── domain/         # Domain models, schemas, services
│   │   ├── ingestion/      # Document ingestion pipeline
│   │   ├── document_processing/  # OCR, extraction, classification
│   │   ├── retrieval/      # Hybrid search, RAG
│   │   ├── ai/             # LLM integration, prompts
│   │   ├── workflow/       # State machines, approvals
│   │   ├── policy/         # RBAC, authorization
│   │   ├── evaluation/     # Testing, golden datasets
│   │   └── observability/  # Logging, tracing, metrics
│   ├── tests/              # Test suite
│   ├── alembic/            # Database migrations
│   ├── pyproject.toml      # Dependencies
│   └── Dockerfile
├── frontend/               # Next.js frontend (placeholder)
├── docs/                   # Documentation
├── infra/                  # Infrastructure as code
├── docker-compose.yml      # Local development stack
├── .env.example            # Environment template
└── README.md
```

## API Endpoints

### Health Checks
- `GET /api/v1/health` - Basic health check
- `GET /api/v1/health/db` - Database connectivity
- `GET /api/v1/health/ready` - Full readiness check

### Planned Endpoints
- `POST /api/v1/auth/login` - Authentication
- `GET/POST /api/v1/projects` - Project management
- `POST /api/v1/documents/upload` - Document upload
- `GET /api/v1/change-orders` - Change order management
- `POST /api/v1/approvals` - Approval workflows
- `POST /api/v1/retrieval/search` - Hybrid search
- `POST /api/v1/ai/analyze` - AI analysis

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/changeguard` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT signing key (32+ chars) | **Required** |
| `STORAGE_ENDPOINT` | MinIO/S3 endpoint | `localhost:9000` |
| `OPENAI_API_KEY` | OpenAI API key | Optional |
| `ANTHROPIC_API_KEY` | Anthropic API key | Optional |

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Code Quality

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy .

# Run tests with coverage
pytest --cov=app --cov-report=html
```

## Architecture Principles

1. **Deterministic systems own facts and actions** - Calculations, deadlines, permissions in code
2. **AI owns interpretation and explanation** - Extraction, classification, drafting via LLMs
3. **Humans own high-risk decisions** - Approvals, financial changes require human review
4. **Tenant isolation at every layer** - API, database, storage, search
5. **Immutable audit trail** - Every action logged with full context

## Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) - System architecture and design
- [`PRD.md`](PRD.md) - Product requirements
- [`DESIGN.md`](DESIGN.md) - UX design and workflows
- [`TEST_PLAN.md`](TEST_PLAN.md) - Testing strategy
- [`SECURITY.md`](SECURITY.md) - Security architecture
- [`DECISIONS.md`](DECISIONS.md) - Architecture decision records

## License

Proprietary - All rights reserved.
