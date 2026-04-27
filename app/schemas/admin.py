from pydantic import BaseModel, Field

from app.schemas.auth import UserOut


class AdminLoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminCreateUserRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=10)
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class AdminUsersResponse(BaseModel):
    users: list[UserOut]
