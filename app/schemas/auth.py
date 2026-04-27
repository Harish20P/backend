from pydantic import BaseModel, Field


class SendOtpRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=10)


class SignupSendOtpRequest(SendOtpRequest):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class VerifyOtpRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=10)
    otp: str = Field(..., min_length=4, max_length=6)


class SignupVerifyOtpRequest(VerifyOtpRequest):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class UserOut(BaseModel):
    id: int
    phone_number: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MessageResponse(BaseModel):
    message: str
