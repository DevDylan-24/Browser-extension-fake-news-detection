"""
models/user.py
==============
User class — handles registration, login, validation, and
MongoDB Atlas persistence for the FactGuard AI extension.

MongoDB setup
─────────────
1. Go to https://cloud.mongodb.com and create a free cluster (M0).
2. In "Database Access", create a database user with a username + password.
3. In "Network Access", add your IP (or 0.0.0.0/0 for development).
4. In "Clusters → Connect → Connect your application", copy the
   connection string. It looks like:
       mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/
5. Paste that string as the value of MONGO_URI in config.py:
       MONGO_URI = "mongodb+srv://youruser:yourpass@cluster0.xxxxx.mongodb.net/"
6. Database name:   factguard
   Collections:     users        ← created automatically on first insert
                    scan_history ← created automatically on first insert
"""

import re
import hashlib
import os
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

# ── Import the MongoDB URI from the config file ───────────────────────────────
# config.py lives in the same directory as server.py and contains:
#   MONGO_URI = "mongodb+srv://user:pass@cluster0.xxxx.mongodb.net/"
from config import MONGO_URI


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE CONNECTION  (module-level singleton — one connection per process)
# ─────────────────────────────────────────────────────────────────────────────
_client = MongoClient(MONGO_URI)
_db     = _client["factguard"]           # database name


class User:
    """
    Represents a FactGuard user account.

    Class attributes
    ────────────────
    collection : pymongo.collection.Collection
        Direct reference to the MongoDB 'users' collection.

    Instance attributes
    ───────────────────
    _id      : str | None   MongoDB ObjectId (string form), None before save
    name     : str          Display name
    email    : str          Unique email address (stored lowercase)
    _pw_hash : str          bcrypt-style SHA-256 hash (hex)
    created_at : datetime   UTC timestamp of account creation
    """

    collection = _db["users"]

    # Ensure email is unique at the database level
    collection.create_index("email", unique=True)

    # ── Validation constants ──────────────────────────────────────────────────
    EMAIL_RE       = re.compile(r'^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}$')
    MIN_PW_LENGTH  = 8
    MAX_PW_LENGTH  = 128
    MIN_NAME_LENGTH = 2
    MAX_NAME_LENGTH = 60

    def __init__(self, name: str, email: str, pw_hash: str,
                 created_at: datetime = None, _id=None):
        self._id        = str(_id) if _id else None
        self.name       = name.strip()
        self.email      = email.strip().lower()
        self._pw_hash   = pw_hash
        self.created_at = created_at or datetime.now(timezone.utc)

    # ── Password hashing ─────────────────────────────────────────────────────

    @staticmethod
    def _hash_password(password: str) -> str:
        """
        SHA-256 hash with a per-application salt derived from the secret key.
        For production, replace with bcrypt:
            import bcrypt
            return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        """
        salt = os.environ.get("SECRET_KEY", "factguard-dev-salt")
        salted = f"{salt}:{password}"
        return hashlib.sha256(salted.encode("utf-8")).hexdigest()

    @staticmethod
    def _verify_password(password: str, pw_hash: str) -> bool:
        return User._hash_password(password) == pw_hash

    # ── Validation ───────────────────────────────────────────────────────────

    @staticmethod
    def validate_name(name: str) -> str | None:
        """Returns an error message string, or None if valid."""
        name = name.strip()
        if len(name) < User.MIN_NAME_LENGTH:
            return f"Name must be at least {User.MIN_NAME_LENGTH} characters."
        if len(name) > User.MAX_NAME_LENGTH:
            return f"Name must be at most {User.MAX_NAME_LENGTH} characters."
        if not re.match(r"^[A-Za-z\s'\-]+$", name):
            return "Name may only contain letters, spaces, hyphens and apostrophes."
        return None

    @staticmethod
    def validate_email(email: str) -> str | None:
        email = email.strip().lower()
        if not email:
            return "Email is required."
        if not User.EMAIL_RE.match(email):
            return "Please enter a valid email address."
        if len(email) > 254:
            return "Email address is too long."
        return None

    @staticmethod
    def validate_password(password: str) -> str | None:
        if len(password) < User.MIN_PW_LENGTH:
            return f"Password must be at least {User.MIN_PW_LENGTH} characters."
        if len(password) > User.MAX_PW_LENGTH:
            return f"Password must be at most {User.MAX_PW_LENGTH} characters."
        if not re.search(r'[A-Z]', password):
            return "Password must contain at least one uppercase letter."
        if not re.search(r'[0-9]', password):
            return "Password must contain at least one number."
        return None

    # ── Factory: register a new user ─────────────────────────────────────────

    @classmethod
    def register(cls, name: str, email: str, password: str,
                 confirm_password: str) -> tuple["User | None", dict]:
        """
        Validate inputs, hash the password, and insert a new user document.

        Returns
        ───────
        (user, errors)
            user   : User instance on success, None on failure
            errors : dict mapping field names to error strings
        """
        errors = {}

        name_err = cls.validate_name(name)
        if name_err:
            errors["name"] = name_err

        email_err = cls.validate_email(email)
        if email_err:
            errors["email"] = email_err

        pw_err = cls.validate_password(password)
        if pw_err:
            errors["password"] = pw_err

        if password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        if errors:
            return None, errors

        pw_hash = cls._hash_password(password)
        user    = cls(name=name, email=email, pw_hash=pw_hash)

        try:
            result = cls.collection.insert_one(user._to_doc())
            user._id = str(result.inserted_id)
            return user, {}
        except DuplicateKeyError:
            return None, {"email": "An account with this email already exists."}

    # ── Factory: authenticate an existing user ────────────────────────────────

    @classmethod
    def login(cls, email: str, password: str) -> tuple["User | None", dict]:
        """
        Look up the user by email and verify the password.

        Returns
        ───────
        (user, errors)
            user   : User instance on success, None on failure
            errors : dict mapping field names to error strings
        """
        errors = {}

        email_err = cls.validate_email(email)
        if email_err:
            errors["email"] = email_err
            return None, errors

        if not password:
            return None, {"password": "Password is required."}

        doc = cls.collection.find_one({"email": email.strip().lower()})
        if not doc:
            # Use a generic message to avoid user enumeration
            return None, {"general": "Invalid email or password."}

        if not cls._verify_password(password, doc["pw_hash"]):
            return None, {"general": "Invalid email or password."}

        return cls._from_doc(doc), {}

    # ── Serialisation helpers ─────────────────────────────────────────────────

    def _to_doc(self) -> dict:
        """Convert to a MongoDB document (no _id — let Mongo generate it)."""
        return {
            "name":       self.name,
            "email":      self.email,
            "pw_hash":    self._pw_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def _from_doc(cls, doc: dict) -> "User":
        return cls(
            name       = doc["name"],
            email      = doc["email"],
            pw_hash    = doc["pw_hash"],
            created_at = doc.get("created_at"),
            _id        = doc["_id"],
        )

    def to_public_dict(self) -> dict:
        """Safe representation to send to the client (no password hash)."""
        return {
            "id":         self._id,
            "name":       self.name,
            "email":      self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
