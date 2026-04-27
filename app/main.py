"""FastAPI entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.session import Base, engine
from app.models import OtpCode, PlanClaim, User, UserSession  # noqa: F401

settings = get_settings()

# Configure logging
logging.basicConfig(level=logging.INFO)


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
	Base.metadata.create_all(bind=engine)
	_ensure_plan_claim_columns()
	yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],  # Allow all origins for development
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
