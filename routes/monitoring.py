import logging

from fastapi import APIRouter, Depends, Request

from core.limiter import custom_rate_limit
from routes.security import admin_auth

log = logging.getLogger("presek.routes.monitoring")
router = APIRouter()


@router.get("/security/status")
@custom_rate_limit("10/minute")
async def get_security_status(request: Request, auth_ok: str = Depends(admin_auth)):
    """Expose secure, rate-limited JSON security health metrics."""
    try:
        from scripts.security_monitoring import SecurityMonitor

        monitor = SecurityMonitor()
        result = monitor.run_comprehensive_check()
        return result
    except Exception as e:
        log.error(f"Failed to generate security health status: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "Failed to run security checks",
            "error": str(e),
        }
