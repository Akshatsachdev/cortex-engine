from __future__ import annotations

import urllib.parse
from typing import Optional

from cortex.tools.browser import fsafe_browser_open


def _gmail_compose_url(
    to: str,
    subject: str = "",
    body: str = "",
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> str:
    base = "https://mail.google.com/mail/"
    params = {
        "view": "cm",
        "fs": "1",
        "to": (to or "").strip(),
        "su": subject or "",
        "body": body or "",
    }
    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc

    return base + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def fsafe_email_compose(
    to: str,
    subject: str = "",
    body: str = "",
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    browser: str = "default",
) -> dict:
    """
    SAFE tool: open a Gmail compose window with prefilled fields.
    Does not send email.
    """
    if not to or not str(to).strip():
        raise ValueError("to is required")

    url = _gmail_compose_url(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    out = fsafe_browser_open(url=url, browser=browser)
    return {
        "compose_url": url,
        "opened": out.get("opened"),
        "browser": out.get("browser", browser),
    }