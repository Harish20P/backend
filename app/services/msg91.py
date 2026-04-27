import logging

import httpx

from app.core.config import get_settings
from app.core.logging_utils import log_operation, mask_otp, mask_phone

logger = logging.getLogger(__name__)


class Msg91Service:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _template_endpoint() -> str:
        return "https://control.msg91.com/api/v5/flow"

    def send_otp(self, phone_number: str, otp_code: str) -> None:
        # Fallback for local development when MSG91 is not configured.
        if not self.settings.msg91_enabled:
            log_operation(logger, "msg91_dev_otp_logged", phone=mask_phone(phone_number), otp=mask_otp(otp_code))
            return

        if not self.settings.msg91_auth_key:
            raise ValueError("MSG91_AUTH_KEY is required when MSG91 is enabled")

        if not self.settings.msg91_template_id:
            raise ValueError("MSG91_TEMPLATE_ID is required when MSG91 is enabled")

        if not self.settings.msg91_sender:
            raise ValueError("MSG91_SENDER is required when MSG91 is enabled")

        payload = {
            "template_id": self.settings.msg91_template_id,
            "sender": self.settings.msg91_sender,
            "sender_id": self.settings.msg91_sender,
            "short_url": "0",
            "mobiles": f"91{phone_number}",
            "OTP": otp_code,
            "otp": otp_code,
            "variables": {"OTP": otp_code},
        }

        headers = {
            "authkey": self.settings.msg91_auth_key,
            "accept": "application/json",
            "content-type": "application/json",
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.post(self._template_endpoint(), headers=headers, json=payload)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "msg91_send_failed | phone=%s status=%s body=%s",
                mask_phone(phone_number),
                response.status_code,
                response.text,
            )
            raise RuntimeError(f"MSG91 template send failed: {response.text}") from exc

        log_operation(
            logger,
            "msg91_send_completed",
            phone=mask_phone(phone_number),
            otp=mask_otp(otp_code),
            template_id=self.settings.msg91_template_id,
        )
