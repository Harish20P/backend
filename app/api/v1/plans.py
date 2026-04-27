import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
import razorpay
from sqlalchemy.orm import Session

from app.api.v1.auth import get_session_from_token
from app.core.config import get_settings
from app.db.session import get_db
from app.models import PlanClaim
from app.schemas import (
    CreateOrderRequest,
    CreateOrderResponse,
    PlanClaimOut,
    PlanClaimsResponse,
    SubmitPlanClaimRequest,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)

router = APIRouter(prefix="/plans", tags=["Plans"])
settings = get_settings()


def claim_to_out(claim: PlanClaim) -> PlanClaimOut:
    return PlanClaimOut(
        id=claim.id,
        user_id=claim.user_id,
        plan_name=claim.plan_name,
        plan_speed=claim.plan_speed,
        monthly_price=claim.monthly_price,
        plan_tier=claim.plan_tier,
        address=claim.address,
        amount_paid=claim.amount_paid,
        payment_status=claim.payment_status,
        paid_at=claim.paid_at,
        activated_at=claim.activated_at,
        expired_at=claim.expired_at,
        created_at=claim.created_at,
    )


def get_razorpay_client() -> tuple[Any, str]:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Razorpay is not configured")

    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret)), settings.razorpay_key_id


def expire_old_activated_plan_claims(db: Session) -> None:
    threshold = datetime.utcnow() - timedelta(days=30)
    expired_claims = (
        db.query(PlanClaim)
        .filter(
            PlanClaim.payment_status == "activated",
            PlanClaim.activated_at != None,
            PlanClaim.activated_at <= threshold,
        )
        .all()
    )
    if not expired_claims:
        return

    for claim in expired_claims:
        claim.payment_status = "expired"
        claim.expired_at = claim.activated_at + timedelta(days=30) if claim.activated_at else datetime.utcnow()
    db.commit()


@router.get("/claims", response_model=PlanClaimsResponse)
def list_my_plan_claims(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> PlanClaimsResponse:
    expire_old_activated_plan_claims(db)
    session = get_session_from_token(db=db, authorization=authorization)
    claims = (
        db.query(PlanClaim)
        .filter(PlanClaim.user_id == session.user_id)
        .order_by(PlanClaim.created_at.desc())
        .all()
    )
    return PlanClaimsResponse(claims=[claim_to_out(claim) for claim in claims])


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    payload: CreateOrderRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> CreateOrderResponse:
    get_session_from_token(db=db, authorization=authorization)

    if payload.amount < 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be at least 100 paise")

    client, key_id = get_razorpay_client()

    try:
        order = client.order.create(
            {
                "amount": payload.amount,
                "currency": payload.currency.upper(),
                "receipt": payload.receipt,
            }
        )
    except Exception as exc:  # noqa: BLE001
        status_code = getattr(exc, "status_code", None)
        error_message = str(exc)
        if status_code == 401 or "401" in error_message:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Razorpay authentication failed") from exc
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create Razorpay order") from exc

    return CreateOrderResponse(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=key_id,
    )


@router.post("/verify-payment", response_model=VerifyPaymentResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> VerifyPaymentResponse:
    session = get_session_from_token(db=db, authorization=authorization)

    if not payload.razorpay_order_id or not payload.razorpay_payment_id or not payload.razorpay_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required payment fields")

    if not settings.razorpay_key_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Razorpay is not configured")

    signed_payload = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"
    generated_signature = hmac.new(
        settings.razorpay_key_secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(generated_signature, payload.razorpay_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Signature mismatch")

    claim = PlanClaim(
        user_id=session.user_id,
        plan_name=payload.plan_name.strip(),
        plan_speed=payload.plan_speed.strip() if payload.plan_speed else None,
        monthly_price=payload.monthly_price,
        plan_tier=payload.plan_tier.strip() if payload.plan_tier else None,
        address=payload.address.strip(),
        amount_paid=payload.amount_paid if payload.amount_paid is not None else payload.monthly_price,
        payment_status="paid",
        paid_at=datetime.utcnow(),
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    return VerifyPaymentResponse(success=True, claim=claim_to_out(claim))


@router.post("/claims", response_model=PlanClaimOut)
def submit_plan_claim(
    payload: SubmitPlanClaimRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> PlanClaimOut:
    session = get_session_from_token(db=db, authorization=authorization)

    claim = PlanClaim(
        user_id=session.user_id,
        plan_name=payload.plan_name.strip(),
        plan_speed=payload.plan_speed.strip() if payload.plan_speed else None,
        monthly_price=payload.monthly_price,
        plan_tier=payload.plan_tier.strip() if payload.plan_tier else None,
        address=payload.address.strip(),
        amount_paid=payload.monthly_price,
        payment_status="submitted",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    return claim_to_out(claim)