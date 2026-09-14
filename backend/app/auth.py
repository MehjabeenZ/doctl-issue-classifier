import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


def _parse_basic_auth(header: str | None) -> tuple[str, str] | None:
    if not header or not header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
    except Exception:
        return None
    username, sep, password = decoded.partition(":")
    if not sep:
        return None
    return username, password


class DemoBasicAuthMiddleware(BaseHTTPMiddleware):
    """Gates the entire app behind HTTP Basic Auth when demo_username/demo_password
    are both set — used only on the hosted Render deployment so a public URL
    with a real, billed SI key behind it isn't wide open to anyone who finds
    the link. Deliberately a no-op when either is unset (empty string, the
    default), so local dev and Docker runs are never affected — this only
    ever activates via explicit env vars set on the hosted instance.
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.demo_username or not settings.demo_password:
            return await call_next(request)

        creds = _parse_basic_auth(request.headers.get("authorization"))
        if creds:
            username, password = creds
            # Constant-time comparison — this gate gets checked on every request
            # to a real, billed backend, so a timing side-channel on the
            # password check is worth avoiding even for a small-scale demo.
            if secrets.compare_digest(username, settings.demo_username) and secrets.compare_digest(
                password, settings.demo_password
            ):
                return await call_next(request)

        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="doctl eval demo"'})
