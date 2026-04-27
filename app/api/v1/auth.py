from datetime import datetime, timedelta
import hashlib
import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_utils import log_operation, mask_otp, mask_phone
from app.db.session import get_db
from app.models import OtpCode, User, UserSession
from app.schemas import (
    AuthResponse,
    MessageResponse,
    SendOtpRequest,
    SignupSendOtpRequest,
    SignupVerifyOtpRequest,
    UserOut,
    VerifyOtpRequest,
)
from app.services import Msg91Service

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()
msg91_service = Msg91Service()
logger = logging.getLogger(__name__)


def normalize_phone(phone_number: str) -> str:
    digits = "".join(ch for ch in phone_number if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    if len(digits) != 10:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Phone number must be 10 digits")

    return digits


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_otp(db: Session, phone_number: str, purpose: str) -> str:
    code = f"{secrets.randbelow(900000) + 100000}"
    otp = OtpCode(
        phone_number=phone_number,
        purpose=purpose,
        code_hash=hash_value(code),
        expires_at=datetime.utcnow() + timedelta(minutes=settings.otp_expiry_minutes),
    )
    db.add(otp)
    db.commit()
    return code


def get_valid_otp(db: Session, phone_number: str, purpose: str, otp: str) -> OtpCode | None:
    return (
        db.query(OtpCode)
        .filter(
            and_(
                OtpCode.phone_number == phone_number,
                OtpCode.purpose == purpose,
                OtpCode.code_hash == hash_value(otp),
                OtpCode.is_consumed.is_(False),
                OtpCode.expires_at > datetime.utcnow(),
            )
        )
        .order_by(desc(OtpCode.created_at))
        .first()
    )


def create_session(db: Session, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    session = UserSession(
        user_id=user_id,
        token_hash=hash_value(raw_token),
        expires_at=datetime.utcnow() + timedelta(days=settings.session_expiry_days),
    )
    db.add(session)
    db.commit()
    return raw_token


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        phone_number=user.phone_number,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
    )


def get_session_from_token(db: Session, authorization: str | None) -> UserSession:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    token_hash = hash_value(token)
    session = (
        db.query(UserSession)
        .filter(
            and_(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > datetime.utcnow(),
            )
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")

    return session


@router.post("/signup/send-otp", response_model=MessageResponse)
def signup_send_otp(payload: SignupSendOtpRequest, db: Session = Depends(get_db)) -> MessageResponse:
    phone = normalize_phone(payload.phone_number)
    log_operation(logger, "signup_send_otp_requested", phone=mask_phone(phone))

    existing_user = db.query(User).filter(User.phone_number == phone).first()
    if existing_user:
        log_operation(logger, "signup_send_otp_blocked", phone=mask_phone(phone), reason="user_exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists. Please login.")

    otp_code = create_otp(db=db, phone_number=phone, purpose="signup")
    log_operation(logger, "signup_otp_generated", phone=mask_phone(phone), otp=mask_otp(otp_code))
    msg91_service.send_otp(phone_number=phone, otp_code=otp_code)
    log_operation(logger, "signup_send_otp_completed", phone=mask_phone(phone))
    return MessageResponse(message="OTP sent successfully")


@router.post("/signup/verify-otp", response_model=AuthResponse)
def signup_verify_otp(payload: SignupVerifyOtpRequest, db: Session = Depends(get_db)) -> AuthResponse:
    phone = normalize_phone(payload.phone_number)
    log_operation(logger, "signup_verify_otp_requested", phone=mask_phone(phone), otp=mask_otp(payload.otp))
    otp_record = get_valid_otp(db=db, phone_number=phone, purpose="signup", otp=payload.otp)

    if not otp_record:
        log_operation(logger, "signup_verify_otp_failed", phone=mask_phone(phone), reason="invalid_or_expired_otp")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    existing_user = db.query(User).filter(User.phone_number == phone).first()
    if existing_user:
        log_operation(logger, "signup_verify_otp_blocked", phone=mask_phone(phone), reason="user_exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists. Please login.")

    otp_record.is_consumed = True

    user = User(
        phone_number=phone,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_session(db=db, user_id=user.id)
    log_operation(logger, "signup_verify_otp_completed", phone=mask_phone(phone), user_id=user.id)

    return AuthResponse(access_token=access_token, user=user_to_out(user))


@router.post("/login/send-otp", response_model=MessageResponse)
def login_send_otp(payload: SendOtpRequest, db: Session = Depends(get_db)) -> MessageResponse:
    phone = normalize_phone(payload.phone_number)
    log_operation(logger, "login_send_otp_requested", phone=mask_phone(phone))

    existing_user = db.query(User).filter(User.phone_number == phone).first()
    if not existing_user:
        log_operation(logger, "login_send_otp_blocked", phone=mask_phone(phone), reason="user_not_found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found. Please signup first.")

    otp_code = create_otp(db=db, phone_number=phone, purpose="login")
    log_operation(logger, "login_otp_generated", phone=mask_phone(phone), otp=mask_otp(otp_code))
    msg91_service.send_otp(phone_number=phone, otp_code=otp_code)
    log_operation(logger, "login_send_otp_completed", phone=mask_phone(phone))
    return MessageResponse(message="OTP sent successfully")


@router.post("/login/verify-otp", response_model=AuthResponse)
def login_verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)) -> AuthResponse:
    phone = normalize_phone(payload.phone_number)
    log_operation(logger, "login_verify_otp_requested", phone=mask_phone(phone), otp=mask_otp(payload.otp))
    otp_record = get_valid_otp(db=db, phone_number=phone, purpose="login", otp=payload.otp)

    if not otp_record:
        log_operation(logger, "login_verify_otp_failed", phone=mask_phone(phone), reason="invalid_or_expired_otp")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    user = db.query(User).filter(User.phone_number == phone).first()
    if not user:
        log_operation(logger, "login_verify_otp_blocked", phone=mask_phone(phone), reason="user_not_found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found. Please signup first.")

    otp_record.is_consumed = True
    db.commit()

    access_token = create_session(db=db, user_id=user.id)
    log_operation(logger, "login_verify_otp_completed", phone=mask_phone(phone), user_id=user.id)
    return AuthResponse(access_token=access_token, user=user_to_out(user))


@router.get("/session/me", response_model=UserOut)
def session_me(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> UserOut:
    session = get_session_from_token(db=db, authorization=authorization)
    user = db.query(User).filter(User.id == session.user_id).first()

    if not user:
        log_operation(logger, "session_me_failed", user_id=session.user_id, reason="user_not_found")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found for session")

    log_operation(logger, "session_me_completed", user_id=user.id, phone=mask_phone(user.phone_number))
    return user_to_out(user)


@router.post("/logout", response_model=MessageResponse)
def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> MessageResponse:
    session = get_session_from_token(db=db, authorization=authorization)
    session.revoked_at = datetime.utcnow()
    db.commit()
    log_operation(logger, "logout_completed", user_id=session.user_id)
    return MessageResponse(message="Logged out successfully")
