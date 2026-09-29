"""
app/extensions.py
Flask extension instances (initialized in app factory).
"""
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

# Core extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)
cors = CORS()

# JWT token blocklist (in-memory for dev; use Redis in production)
jwt_blocklist = set()
