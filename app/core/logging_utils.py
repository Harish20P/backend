"""Logging helpers for request and operation audit logs."""

from __future__ import annotations

import logging.config
import logging
import uuid
from typing import Any


def configure_logging() -> None:
	"""Configure a consistent log format for the application."""

	logging.config.dictConfig(
		{
			"version": 1,
			"disable_existing_loggers": False,
			"formatters": {
				"default": {
					"format": "%(asctime)s %(levelname)s %(name)s %(message)s",
				}
			},
			"handlers": {
				"stdout": {
					"class": "logging.StreamHandler",
					"formatter": "default",
					"stream": "ext://sys.stdout",
				},
			},
			"root": {
				"level": "INFO",
				"handlers": ["stdout"],
			},
			"loggers": {
				"uvicorn": {
					"level": "INFO",
					"handlers": ["stdout"],
					"propagate": False,
				},
				"uvicorn.error": {
					"level": "INFO",
					"handlers": ["stdout"],
					"propagate": False,
				},
				"uvicorn.access": {
					"level": "INFO",
					"handlers": ["stdout"],
					"propagate": False,
				},
			},
		}
	)


def get_request_id() -> str:
	"""Return a short request identifier for correlating log lines."""

	return uuid.uuid4().hex[:12]


def mask_phone(phone_number: str | None) -> str:
	"""Mask a phone number for safe logging."""

	if not phone_number:
		return "unknown"

	digits = "".join(ch for ch in phone_number if ch.isdigit())
	if len(digits) <= 4:
		return "*" * len(digits)

	return f"{digits[:2]}******{digits[-2:]}"


def mask_email(email: str | None) -> str:
	"""Mask an email address for safe logging."""

	if not email:
		return "unknown"

	if "@" not in email:
		return "***"

	local_part, domain = email.split("@", 1)
	if not local_part:
		masked_local = "***"
	elif len(local_part) <= 2:
		masked_local = local_part[0] + "*"
	else:
		masked_local = f"{local_part[:2]}***"

	return f"{masked_local}@{domain}"


def mask_otp(otp: str | None) -> str:
	"""Return an OTP value for logging."""

	if not otp:
		return "unknown"

	return otp


def log_operation(logger: logging.Logger, message: str, **fields: Any) -> None:
	"""Log an operation with compact key=value fields."""

	parts = [message]
	for key, value in fields.items():
		parts.append(f"{key}={value}")
	logger.info(" | ".join(parts))