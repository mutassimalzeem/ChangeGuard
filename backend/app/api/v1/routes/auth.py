"""Generic responses and explicit commits preserve failed-login audits and limits."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.reset_mail import PasswordResetMailer, get_password_reset_mailer
from app.domain.schemas.auth import (
    Identity,
    Login,
    Message,
    Refresh,
    Register,
    ResetConfirm,
    TokenPair,
)
from app.domain.services.authentication import AuthenticationService, AuthFailure


class AuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                # FastAPI's default validation response echoes rejected secret input.
                response = JSONResponse(
                    {"detail": "Invalid authentication request"}, status_code=422
                )
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return response

        return safe_handler


router = APIRouter(route_class=AuthRoute, tags=["authentication"])


def get_auth_service(request: Request, session: AsyncSession = Depends(get_session)):
    return AuthenticationService(session, request)


async def execute(service, operation):
    try:
        result = await operation
    except AuthFailure as exc:
        # Raising HTTPException would make get_session roll back the security event.
        await service.session.commit()
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if exc.status == 401
            else {"Retry-After": str(get_settings().login_window_seconds)}
        )
        return JSONResponse(
            {
                "detail": "Authentication failed"
                if exc.status == 401
                else "Too many authentication attempts"
            },
            status_code=exc.status,
            headers=headers,
        )
    await service.session.commit()
    return result


@router.post("/register", response_model=Message, status_code=202)
async def register(payload: Register, service: AuthenticationService = Depends(get_auth_service)):
    result = await execute(service, service.register(payload))
    return (
        result
        if isinstance(result, Response)
        else Message(
            message="If registration can be completed, you can sign in with the supplied details."
        )
    )


@router.post("/login", response_model=TokenPair)
async def login(payload: Login, service: AuthenticationService = Depends(get_auth_service)):
    return await execute(service, service.login(payload))


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: Refresh, service: AuthenticationService = Depends(get_auth_service)):
    return await execute(service, service.refresh(payload.refresh_token.get_secret_value()))


@router.post("/logout", status_code=204)
async def logout(payload: Refresh, service: AuthenticationService = Depends(get_auth_service)):
    result = await execute(service, service.logout(payload.refresh_token.get_secret_value()))
    return result if isinstance(result, Response) else Response(status_code=204)


@router.post("/password-reset/request", response_model=Message, status_code=202)
async def request_password_reset(
    payload: Identity,
    tasks: BackgroundTasks,
    service: AuthenticationService = Depends(get_auth_service),
    mailer: PasswordResetMailer = Depends(get_password_reset_mailer),
):
    result = await execute(service, service.request_reset(payload))
    if isinstance(result, Response):
        return result
    if result:
        mailer.queue(tasks, *result)
    return Message(message="If the account exists, password reset instructions will be sent.")


@router.post("/password-reset/confirm", response_model=Message)
async def confirm_password_reset(
    payload: ResetConfirm, service: AuthenticationService = Depends(get_auth_service)
):
    result = await execute(service, service.confirm_reset(payload))
    return (
        result
        if isinstance(result, Response)
        else Message(message="Password reset completed. Please sign in.")
    )
