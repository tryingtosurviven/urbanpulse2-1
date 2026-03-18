"""
auth.py — UrbanPulse R3 Authentication & RBAC
IM8-aligned JWT-based role enforcement.

Roles:
  citizen        → /citizen (read-only)
  clinic_manager → /clinic, /logistics, clinic API endpoints
  admin          → /admin + all endpoints

Usage in app.py:
  from auth import require_role, login_endpoint
  app.register_blueprint(login_endpoint)

  @app.route("/clinic")
  @require_role("clinic_manager", "admin")
  def clinic_portal(): ...
"""

import os
import datetime
import functools
import jwt
from flask import Blueprint, request, jsonify, redirect, url_for

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
JWT_SECRET = os.environ.get("JWT_SECRET", "urbanpulse-dev-secret-CHANGE-IN-PROD")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8  # Matches a standard shift for clinic staff

# ---------------------------------------------------------------------------
# DEMO USER STORE
# In production: replace with SingPass/Corppass OAuth2 or LDAP lookup.
# Passwords are plaintext here for demo only — use bcrypt in production.
# ---------------------------------------------------------------------------
DEMO_USERS = {
    "citizen01":        {"password": "citizen123",  "role": "citizen",        "name": "Tan Mei Ling"},
    "clinic_manager01": {"password": "clinic123",   "role": "clinic_manager", "name": "Dr. Rajesh Kumar"},
    "admin01":          {"password": "admin123",    "role": "admin",          "name": "System Admin"},
}

# ---------------------------------------------------------------------------
# ROLE HIERARCHY — higher index = more privileged
# ---------------------------------------------------------------------------
ROLE_LEVEL = {"citizen": 0, "clinic_manager": 1, "admin": 2}

# ---------------------------------------------------------------------------
# TOKEN UTILITIES
# ---------------------------------------------------------------------------

def generate_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
        # IM8 audit field: include issuer
        "iss": "urbanpulse-r3",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None  # Expired
    except jwt.InvalidTokenError:
        return None  # Tampered / invalid


def get_token_from_request() -> str | None:
    """Extract JWT from Authorization header or session cookie."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    # Fallback: cookie (for browser portals)
    return request.cookies.get("urbanpulse_token")


# ---------------------------------------------------------------------------
# DECORATOR: require_role
# ---------------------------------------------------------------------------

def require_role(*allowed_roles: str):
    """
    Decorator to protect Flask routes by role.

    Usage:
        @app.route("/clinic")
        @require_role("clinic_manager", "admin")
        def clinic_portal(): ...

    For API endpoints: returns 401/403 JSON.
    For page routes: redirects to /login.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            token = get_token_from_request()

            if not token:
                if _is_api_route():
                    return jsonify({"error": "Unauthorized", "code": "NO_TOKEN"}), 401
                return redirect(f"/login?next={request.path}")

            payload = decode_token(token)
            if not payload:
                if _is_api_route():
                    return jsonify({"error": "Token expired or invalid", "code": "BAD_TOKEN"}), 401
                return redirect(f"/login?next={request.path}&reason=expired")

            user_role = payload.get("role", "")
            if user_role not in allowed_roles:
                if _is_api_route():
                    return jsonify({
                        "error": "Forbidden",
                        "code": "INSUFFICIENT_ROLE",
                        "required": list(allowed_roles),
                        "current": user_role
                    }), 403
                # Page: show a friendly access-denied instead of blank redirect
                return redirect("/access-denied")

            # Attach user context to request for use in route handlers
            request.current_user = {
                "username": payload["sub"],
                "role": user_role,
                "name": DEMO_USERS.get(payload["sub"], {}).get("name", payload["sub"]),
            }
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _is_api_route() -> bool:
    return request.path.startswith("/api/")


# ---------------------------------------------------------------------------
# BLUEPRINT: Login / Logout endpoints
# ---------------------------------------------------------------------------
login_endpoint = Blueprint("auth", __name__)


@login_endpoint.post("/api/auth/login")
def api_login():
    """
    POST /api/auth/login
    Body: { "username": "...", "password": "..." }
    Returns: { "token": "...", "role": "...", "name": "..." }

    This is the endpoint your login.html form POSTs to.
    In production: replace DEMO_USERS lookup with Corppass OIDC token exchange.
    """
    body = request.json or {}
    username = body.get("username", "").strip()
    password = body.get("password", "")

    user = DEMO_USERS.get(username)
    if not user or user["password"] != password:
        # IM8: don't reveal which field was wrong
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(username, user["role"])

    # Audit log (in production: write to persistent store)
    print(f"[AUTH] Login: user={username} role={user['role']} ip={request.remote_addr}")

    return jsonify({
        "token": token,
        "role": user["role"],
        "name": user["name"],
        "expires_in": JWT_EXPIRY_HOURS * 3600,
    })


@login_endpoint.post("/api/auth/logout")
def api_logout():
    """
    Stateless JWT: logout is client-side token deletion.
    In production: add token to a Redis blocklist for the remaining TTL.
    """
    username = "unknown"
    token = get_token_from_request()
    if token:
        payload = decode_token(token)
        if payload:
            username = payload.get("sub", "unknown")
    print(f"[AUTH] Logout: user={username}")
    return jsonify({"status": "logged_out"})


@login_endpoint.get("/api/auth/me")
def api_me():
    """Returns current user context — used by portals to personalise UI."""
    token = get_token_from_request()
    if not token:
        return jsonify({"error": "Not authenticated"}), 401
    payload = decode_token(token)
    if not payload:
        return jsonify({"error": "Token expired"}), 401
    return jsonify({
        "username": payload["sub"],
        "role": payload["role"],
        "name": DEMO_USERS.get(payload["sub"], {}).get("name", payload["sub"]),
    })
