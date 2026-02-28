import os
import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Optional

DEFAULT_ITERS = 200_000
SALT_BYTES = 16
DKLEN = 32


@dataclass(frozen=True)
class PasswordHash:
    algo: str
    iters: int
    salt_b64: str
    dk_b64: str

    def to_string(self) -> str:
        # format: pbkdf2_sha256$200000$<salt_b64>$<dk_b64>
        return f"{self.algo}${self.iters}${self.salt_b64}${self.dk_b64}"

    @staticmethod
    def from_string(s: str) -> "PasswordHash":
        parts = s.split("$")
        if len(parts) != 4:
            raise ValueError("Invalid password hash format")
        algo, iters_s, salt_b64, dk_b64 = parts
        return PasswordHash(algo=algo, iters=int(iters_s), salt_b64=salt_b64, dk_b64=dk_b64)


def hash_password(password: str, *, iters: int = DEFAULT_ITERS) -> str:
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    salt = os.urandom(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(
        "utf-8"), salt, iters, dklen=DKLEN)

    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(dk).decode("ascii")

    return PasswordHash(
        algo="pbkdf2_sha256",
        iters=iters,
        salt_b64=salt_b64,
        dk_b64=dk_b64,
    ).to_string()


def verify_password(password: str, stored: str) -> bool:
    try:
        ph = PasswordHash.from_string(stored)
        if ph.algo != "pbkdf2_sha256":
            return False

        salt = base64.b64decode(ph.salt_b64.encode("ascii"))
        dk_expected = base64.b64decode(ph.dk_b64.encode("ascii"))

        dk = hashlib.pbkdf2_hmac("sha256", password.encode(
            "utf-8"), salt, ph.iters, dklen=len(dk_expected))
        return hmac.compare_digest(dk, dk_expected)
    except Exception:
        return False
