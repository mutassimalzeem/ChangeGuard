"""Main API v1 router."""

from fastapi import APIRouter

from app.api.v1.routes import auth, documents, health, projects

api_router = APIRouter()
api_router.include_router(documents.router)
api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(projects.router, prefix="", tags=["projects"])

# Placeholder for other routers
# api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
# api_router.include_router(change_orders.router, prefix="/change-orders", tags=["change-orders"])
# api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
# api_router.include_router(retrieval.router, prefix="/retrieval", tags=["retrieval"])
# api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
