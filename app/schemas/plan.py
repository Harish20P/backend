from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.auth import UserOut


class SubmitPlanClaimRequest(BaseModel):
    plan_name: str = Field(..., min_length=1, max_length=120)
    plan_speed: str | None = Field(default=None, max_length=120)
    monthly_price: int | None = Field(default=None, ge=0)
    plan_tier: str | None = Field(default=None, max_length=30)
    address: str = Field(..., min_length=5, max_length=600)


class PlanClaimOut(BaseModel):
    id: int
    user_id: int
    plan_name: str
    plan_speed: str | None = None
    monthly_price: int | None = None
    plan_tier: str | None = None
    address: str
    amount_paid: int | None = None
    payment_status: str = "submitted"
    paid_at: datetime | None = None
    activated_at: datetime | None = None
    expired_at: datetime | None = None
    created_at: datetime


class PlanClaimsResponse(BaseModel):
    claims: list[PlanClaimOut]


class CreateOrderRequest(BaseModel):
    amount: int = Field(..., ge=100)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    receipt: str = Field(..., min_length=1, max_length=120)


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str = Field(..., min_length=1)
    razorpay_order_id: str = Field(..., min_length=1)
    razorpay_signature: str = Field(..., min_length=1)
    amount_paid: int | None = Field(default=None, ge=0)
    plan_name: str = Field(..., min_length=1, max_length=120)
    plan_speed: str | None = Field(default=None, max_length=120)
    monthly_price: int | None = Field(default=None, ge=0)
    plan_tier: str | None = Field(default=None, max_length=30)
    address: str = Field(..., min_length=5, max_length=600)


class VerifyPaymentResponse(BaseModel):
    success: bool
    claim: PlanClaimOut


class AdminUserClaimsResponse(BaseModel):
    user: UserOut
    claims: list[PlanClaimOut]