"""Application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	"""Environment-driven settings for API, DB, auth, and MSG91."""

	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

	app_name: str = "MyVeltrak API"
	api_v1_prefix: str = "/api/v1"
	database_url: str = Field(default="sqlite:///./myveltrak.db", alias="DATABASE_URL")

	otp_expiry_minutes: int = 5
	session_expiry_days: int = 30
	admin_email: str = Field(default="admin@gmail.com", alias="ADMIN_EMAIL")
	admin_password: str = Field(default="admin@123", alias="ADMIN_PASSWORD")
	admin_token_secret: str = Field(default="myveltrak-admin-secret", alias="ADMIN_TOKEN_SECRET")
	admin_token_expiry_minutes: int = Field(default=1440, alias="ADMIN_TOKEN_EXPIRY_MINUTES")

	msg91_auth_key: str | None = Field(default=None, alias="MSG91_AUTH_KEY")
	msg91_template_id: str | None = Field(default=None, alias="MSG91_TEMPLATE_ID")
	msg91_sender: str | None = Field(default=None, alias="MSG91_SENDER")
	msg91_route: str = Field(default="4", alias="MSG91_ROUTE")
	msg91_enabled: bool = Field(default=False, alias="MSG91_ENABLED")
	razorpay_key_id: str | None = Field(default=None, alias="RAZORPAY_KEY_ID")
	razorpay_key_secret: str | None = Field(default=None, alias="RAZORPAY_KEY_SECRET")


@lru_cache
def get_settings() -> Settings:
	"""Return cached settings."""

	return Settings()
