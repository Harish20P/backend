"""FastAPI entrypoint."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging_utils import configure_logging, get_request_id
from app.db.session import Base, engine
from app.models import OtpCode, PlanClaim, User, UserSession  # noqa: F401

settings = get_settings()
logger = logging.getLogger(__name__)

configure_logging()


def _ensure_plan_claim_columns() -> None:
	if engine.dialect.name != "sqlite":
		return

	with engine.connect() as connection:
		inspector = inspect(connection)
		if not inspector.has_table("plan_claims"):
			return

		columns = {column["name"] for column in inspector.get_columns("plan_claims")}
		missing_columns = [
			(column_name, column_definition)
			for column_name, column_definition in (
				("amount_paid", "INTEGER"),
				("payment_status", "VARCHAR(20) NOT NULL DEFAULT 'submitted'"),
				("paid_at", "DATETIME"),
				("activated_at", "DATETIME"),
				("expired_at", "DATETIME"),
				("razorpay_order_id", "VARCHAR(100)"),
				("razorpay_payment_id", "VARCHAR(100)"),
				("razorpay_signature", "VARCHAR(200)"),
			)
			if column_name not in columns
		]

	if not missing_columns:
		return

	with engine.begin() as connection:
		for column_name, column_definition in missing_columns:
			connection.exec_driver_sql(f"ALTER TABLE plan_claims ADD COLUMN {column_name} {column_definition}")


@asynccontextmanager
async def lifespan(_: FastAPI):
	logger.info("application_starting | app_name=%s", settings.app_name)
	Base.metadata.create_all(bind=engine)
	_ensure_plan_claim_columns()
	logger.info("application_ready | database=%s", engine.url.drivername)
	yield
	logger.info("application_stopping")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],  # Allow all origins for development
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
	request_id = get_request_id()
	start_time = time.perf_counter()
	client_host = request.client.host if request.client else "unknown"
	logger.info(
		"request_started | request_id=%s method=%s path=%s client=%s",
		request_id,
		request.method,
		request.url.path,
		client_host,
	)
	try:
		response = await call_next(request)
	except Exception:
		duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
		logger.exception(
			"request_failed | request_id=%s method=%s path=%s duration_ms=%s",
			request_id,
			request.method,
			request.url.path,
			duration_ms,
		)
		raise

	duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
	logger.info(
		"request_finished | request_id=%s method=%s path=%s status_code=%s duration_ms=%s",
		request_id,
		request.method,
		request.url.path,
		response.status_code,
		duration_ms,
	)
	response.headers["X-Request-ID"] = request_id
	return response

app.include_router(api_router, prefix=settings.api_v1_prefix)
