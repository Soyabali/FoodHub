"""
auth.py (router) - the URLs for registration, login and passwords.

Routers stay thin: they receive the request, call a service function,
and return the result. The real logic lives in app/services/.
"""
from fastapi import APIRouter, status

from app.database import DB
from app.dependencies import CurrentUser
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentCustomer,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services import auth_service, password_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------- Step 5: registration and login ----------

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, conn: DB):
    customer = auth_service.register_customer(conn, data)
    return {"message": "Registration successful. You can now log in.", "customer": customer}


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, conn: DB):
    """Log in with email and password. Copy the access_token from the
    response, click 'Authorize' at the top of Swagger and paste it."""
    return auth_service.login_customer(conn, data.email, data.password)


@router.get("/me", response_model=CurrentCustomer)
def read_me(customer: CurrentUser):
    return customer


# ---------- Step 6: password management ----------

@router.post("/forgot-password", response_model=ForgotPasswordResponse, response_model_exclude_none=True)
def forgot_password(data: ForgotPasswordRequest, conn: DB):
    return password_service.forgot_password(conn, data.email)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest, conn: DB):
    password_service.reset_password(conn, data.reset_token, data.new_password)
    return {"message": "Password has been reset. You can now log in with your new password."}


@router.post("/change-password", response_model=MessageResponse)
def change_password(data: ChangePasswordRequest, customer: CurrentUser, conn: DB):
    password_service.change_password(conn, customer["customer_id"], data.current_password, data.new_password)
    return {"message": "Password changed successfully."}
