import asyncio
from contextlib import asynccontextmanager, suppress
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api.routes import router
from app.core.config import Settings
from app.core.errors import KycError
from app.core.middleware import RequestMiddleware, configure_logging
from app.models.schemas import ErrorResponse
from app.services.kyc_service import KycService


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup fails if a configured model is missing or has the wrong shape.
        app.state.kyc = KycService(config)

        async def cleanup() -> None:
            while True:
                await asyncio.sleep(30)
                await asyncio.to_thread(app.state.kyc.store.prune)

        task = asyncio.create_task(cleanup())
        logging.getLogger("kyc").info("startup", extra={"event": "startup", "mode": config.mode})
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            app.state.kyc.close()

    app = FastAPI(title="Vision KYC", version="1.0.0", lifespan=lifespan,
                  responses={code: {"model": ErrorResponse} for code in (401, 409, 410, 413, 415, 422, 429, 500, 503)})
    app.add_middleware(RequestMiddleware, max_bytes=config.max_request_bytes)
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins,
                       allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Content-Type", "Authorization"], expose_headers=["X-Request-ID"])

    def error_response(request: Request, code: str, message: str, status: int) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        logging.getLogger("kyc").warning("request_error", extra={
            "event": "request_error", "request_id": request_id, "error_code": code, "status": status,
        })
        headers = {"Cache-Control": "no-store", "X-Request-ID": request_id}
        if status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "request_id": request_id,
        }}, headers=headers)

    @app.exception_handler(KycError)
    async def kyc_error(request: Request, error: KycError):
        return error_response(request, error.code, error.message, error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Pydantic's raw error can contain the submitted base64 image: do not
        # echo errors(), request bodies, credentials or biometric input in logs.
        return error_response(request, "validation_error", "Request fields are missing, invalid, or unexpected. See /docs for the schema.", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return error_response(request, "http_error", str(error.detail), error.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        logging.getLogger("kyc").error("unexpected_error", extra={
            "event": "unexpected_error", "request_id": getattr(request.state, "request_id", ""),
            "error_type": type(error).__name__,
        })
        return error_response(request, "internal_error", "Verification could not be completed. Please retry.", 500)

    @app.get("/health", tags=["System"])
    def health() -> dict[str, str | bool]:
        return {"status": "ok", "mode": config.mode,
                "automatic_decisions_enabled": config.mode == "model" and config.thresholds_calibrated,
                "storage": "memory_single_process"}

    app.include_router(router)
    return app


app = create_app()

