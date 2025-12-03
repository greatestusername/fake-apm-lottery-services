from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST


def create_health_router(
    check_ready: callable = None,
    service_name: str = "service"
) -> APIRouter:
    """Create health check router with liveness, readiness, and metrics endpoints."""
    
    router = APIRouter(tags=["health"])
    
    @router.get("/health/live")
    async def liveness():
        return {"status": "ok", "service": service_name}
    
    @router.get("/health/ready")
    async def readiness():
        if check_ready:
            is_ready = await check_ready()
            if not is_ready:
                return Response(
                    content='{"status": "not_ready"}',
                    status_code=503,
                    media_type="application/json"
                )
        return {"status": "ready", "service": service_name}
    
    @router.get("/metrics")
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    
    return router

