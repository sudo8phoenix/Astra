import logging
from time import perf_counter
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from uuid import uuid4

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.logging_config import get_trace_id, setup_json_logging, set_trace_id
from app.core.metrics import metrics_collector
from app.core.rate_limiting import rate_limit_middleware
from app.schemas.common import ApiErrorDetail, ApiErrorResponse

# Initialize structured logging
setup_json_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version=settings.api_version)

# === MIDDLEWARE ===

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    
    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Enable browser XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Strict Transport Security (production only)
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self' wss: https:"
    )
    
    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Permissions Policy
    response.headers["Permissions-Policy"] = (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "payment=()"
    )
    
    return response


# Trace ID middleware
@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Extract or generate trace_id and propagate to context."""
    trace_id = request.headers.get("x-trace-id", str(uuid4()))
    
    # Set in context for all logs in this request
    set_trace_id(trace_id)
    
    # Add to request state for access in handlers
    request.state.trace_id = trace_id
    
    start = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = (perf_counter() - start) * 1000
        metrics_collector.record_http_request(
            path=request.url.path,
            method=request.method,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        logger.info(
            "request.completed",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
    

@app.middleware("http")
async def trace_id_response_header_middleware(request: Request, call_next):
    """Always attach trace id to outgoing response headers."""
    response = await call_next(request)
    trace_id = get_trace_id() or getattr(request.state, "trace_id", None)
    if trace_id:
        response.headers["X-Trace-ID"] = trace_id
    return response


# Rate limiting middleware
@app.middleware("http")
async def apply_rate_limiting(request: Request, call_next):
    """Apply rate limiting to requests."""
    return await rate_limit_middleware(request, call_next)


# === EXCEPTION HANDLERS ===

async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    metrics_collector.increment(
        "http_errors_total",
        labels={"error_type": "http_exception", "status": str(exc.status_code)},
    )
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id")
    error = ApiErrorResponse(
        error_code=f"http_{exc.status_code}",
        message=str(exc.detail),
        trace_id=trace_id,
    )
    return JSONResponse(status_code=exc.status_code, content=error.model_dump())


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    metrics_collector.increment(
        "http_errors_total",
        labels={"error_type": "validation_error", "status": "422"},
    )
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id")
    details = [
        ApiErrorDetail(field=".".join(map(str, err["loc"])), reason=err["msg"])
        for err in exc.errors()
    ]
    error = ApiErrorResponse(
        error_code="validation_error",
        message="Request validation failed",
        details=details,
        trace_id=trace_id,
    )
    return JSONResponse(status_code=422, content=error.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _: Exception) -> JSONResponse:
    metrics_collector.increment(
        "http_errors_total",
        labels={"error_type": "unhandled_exception", "status": "500"},
    )
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id")
    error = ApiErrorResponse(
        error_code="internal_error",
        message="Internal server error",
        trace_id=trace_id,
    )
    return JSONResponse(status_code=500, content=error.model_dump())


app.include_router(v1_router, prefix=f"{settings.api_prefix}/{settings.api_version}")
