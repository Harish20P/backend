# MyVeltrak Backend

FastAPI backend with OTP-based auth for signup and login, session persistence, and MSG91 SMS integration.

## Stack

- FastAPI
- SQLAlchemy
- PostgreSQL (recommended)
- MSG91 for OTP SMS

## Setup

1. Create a `.env` file from `.env.example`.
2. Update the DB and MSG91 variables.
3. Install dependencies and run:

```bash
uv sync
uv run uvicorn app.main:app --reload
```

## Environment Variables

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/myveltrak
MSG91_ENABLED=false
MSG91_AUTH_KEY=
MSG91_TEMPLATE_ID=
MSG91_SENDER=
MSG91_ROUTE=4
```

When `MSG91_ENABLED=false`, OTPs are not sent via SMS and are logged on the server for development.

## Auth Endpoints

- `POST /api/v1/auth/signup/send-otp`
- `POST /api/v1/auth/signup/verify-otp`
- `POST /api/v1/auth/login/send-otp`
- `POST /api/v1/auth/login/verify-otp`
- `GET /api/v1/auth/session/me`
- `POST /api/v1/auth/logout`

## MSG91 SMS Template

Create a DLT-approved OTP template in MSG91 (or your DLT portal) with OTP variable.

Suggested SMS text:

```text
Your MyVeltrak OTP is ##OTP##. It is valid for 5 minutes. Do not share this OTP with anyone.
```

Suggested metadata:

- Template type: OTP / Service implicit
- Variable: `##OTP##`
- Sender ID: use approved sender (for example, `MYVLTK`)

Use the approved MSG91 `template_id` in `MSG91_TEMPLATE_ID`.
