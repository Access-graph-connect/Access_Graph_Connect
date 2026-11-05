"""GitHub webhook signature verification.

Signatures are HMAC-SHA256 over the *raw* request body, compared in
constant time. Verification happens before any state change; an invalid
signature never alters the database.
"""

import hashlib
import hmac


def verify_github_signature(
    secret: str, body: bytes, signature_header: str | None
) -> bool:
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)
