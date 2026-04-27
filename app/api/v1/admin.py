import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import PlanClaim, User
from app.schemas import (
    AdminCreateUserRequest,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserClaimsResponse,
    AdminUsersResponse,
    PlanClaimOut,
    UserOut,
)

router = APIRouter(prefix="/admin", tags=["Admin"])
settings = get_settings()


def normalize_phone(phone_number: str) -> str:
    digits = "".join(ch for ch in phone_number if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    if len(digits) != 10:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Phone number must be 10 digits")

    return digits


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        phone_number=user.phone_number,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
    )


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
        created_at=claim.created_at,
    )


def _b64_encode(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")


def _b64_decode(raw: str) -> str:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("utf-8")).decode("utf-8")


def _sign(payload_b64: str) -> str:
    secret = settings.admin_token_secret.encode("utf-8")
    return hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def create_admin_token(email: str) -> str:
    exp = int(time.time()) + (settings.admin_token_expiry_minutes * 60)
    claims = {"sub": "admin", "email": email, "exp": exp}
    payload_b64 = _b64_encode(json.dumps(claims, separators=(",", ":")))
    signature = _sign(payload_b64)
    return f"{payload_b64}.{signature}"


def verify_admin_token(token: str) -> dict[str, Any]:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token") from exc

    expected_signature = _sign(payload_b64)
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")

    try:
        payload_json = _b64_decode(payload_b64)
        claims = json.loads(payload_json)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token payload") from exc

    if claims.get("sub") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token subject")

    if int(claims.get("exp", 0)) <= int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token expired")

    return claims


def require_admin(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    return verify_admin_token(token)


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest) -> AdminLoginResponse:
    if payload.email.lower() != settings.admin_email.lower() or payload.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")

    token = create_admin_token(settings.admin_email)
    return AdminLoginResponse(access_token=token)


@router.get("/users", response_model=AdminUsersResponse)
def list_users(_: dict[str, Any] = Depends(require_admin), db: Session = Depends(get_db)) -> AdminUsersResponse:
    users = db.query(User).order_by(User.created_at.desc()).all()
    return AdminUsersResponse(users=[user_to_out(user) for user in users])


@router.get("/users/{user_id}/claims", response_model=AdminUserClaimsResponse)
def get_user_claims(
    user_id: int,
    _: dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserClaimsResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    claims = (
        db.query(PlanClaim)
        .filter(PlanClaim.user_id == user_id)
        .order_by(PlanClaim.created_at.desc())
        .all()
    )
    return AdminUserClaimsResponse(user=user_to_out(user), claims=[claim_to_out(claim) for claim in claims])


@router.post("/users/{user_id}/claims/{claim_id}/activate", response_model=PlanClaimOut)
def activate_user_claim(
    user_id: int,
    claim_id: int,
    _: dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PlanClaimOut:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    claim = (
        db.query(PlanClaim)
        .filter(PlanClaim.id == claim_id, PlanClaim.user_id == user_id)
        .first()
    )
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    if claim.payment_status != "paid" and claim.payment_status != "activated":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only paid claims can be activated")

    if claim.payment_status == "activated":
        return claim_to_out(claim)

    claim.payment_status = "activated"
    claim.activated_at = datetime.utcnow()
    db.commit()
    db.refresh(claim)
    return claim_to_out(claim)


@router.post("/users", response_model=UserOut)
def create_user(
    payload: AdminCreateUserRequest,
    _: dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    phone = normalize_phone(payload.phone_number)

    existing_user = db.query(User).filter(User.phone_number == phone).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = User(
        phone_number=phone,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email) if payload.email else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_out(user)
