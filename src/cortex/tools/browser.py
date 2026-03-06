from __future__ import annotations

import ipaddress
import socket
import urllib.request
import urllib.parse
import webbrowser
from typing import Optional

import subprocess
import shutil

from cortex.runtime.config import load_config

import os
import platform
import shutil
import subprocess
from pathlib import Path
import webbrowser


class BrowserBlocked(Exception):
    pass


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except ValueError:
        return True


def _resolve_host_ips(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    ips: list[str] = []
    for fam, _, _, _, sockaddr in infos:
        if fam == socket.AF_INET:
            ips.append(sockaddr[0])
        elif fam == socket.AF_INET6:
            ips.append(sockaddr[0])
    return sorted(set(ips))


def _domain_matches(host: str, rule: str) -> bool:
    host = host.lower().strip(".")
    rule = rule.lower().strip(".")
    return host == rule or host.endswith("." + rule)


def _normalize_url(raw: str) -> str:
    s = (raw or "").strip()

    # If user types "youtube.com" or "www.youtube.com", treat as https://
    if "://" not in s:
        s = "https://" + s

    # Handle cases like "https://youtube.com/something"
    p = urllib.parse.urlparse(s)

    # If user typed something weird that ended up in path, try to recover
    if not p.hostname and p.path and "." in p.path and " " not in p.path:
        s2 = "https://" + p.path
        p2 = urllib.parse.urlparse(s2)
        if p2.hostname:
            return s2

    return s


def _validate_target(url: str) -> urllib.parse.ParseResult:
    cfg = load_config()
    b = cfg.get("browser") or {}

    if not b.get("enabled", False):
        raise BrowserBlocked("browser tools are disabled by config")

    # empty => allow all public
    allowed_domains = b.get("allowed_domains") or []
    blocked_domains = b.get("blocked_domains") or []

    p = urllib.parse.urlparse(url)

    if p.scheme not in ("http", "https"):
        raise BrowserBlocked("Only http/https URLs are allowed")

    if not p.hostname:
        raise BrowserBlocked("URL must include a hostname")

    host = p.hostname.lower().strip(".")

    # Block localhost names
    if host in {"localhost"}:
        raise BrowserBlocked("localhost is blocked")

    # Explicit blocked domains
    for bd in blocked_domains:
        if _domain_matches(host, bd):
            raise BrowserBlocked(f"Domain blocked: {host}")

    # Allowlist only if configured (empty means allow all public)
    if allowed_domains:
        ok = any(_domain_matches(host, ad) for ad in allowed_domains)
        if not ok:
            raise BrowserBlocked(
                f"Domain not allowed: {host} (allowed_domains={allowed_domains})")

    # Resolve and block private/internal ranges
    ips = _resolve_host_ips(host)
    if not ips:
        raise BrowserBlocked("Could not resolve host")

    for ip in ips:
        if _is_private_ip(ip):
            raise BrowserBlocked(f"Resolved to blocked IP: {ip}")

    return p


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fsafe_browser_fetch(url: str) -> dict:
    """
    SAFE tool: fetch URL content with strict security controls.
    Allows all PUBLIC domains by default (unless allowed_domains is set).
    Blocks localhost/private IPs. Enforces timeouts/size/content-type.
    """
    cfg = load_config()
    b = cfg.get("browser") or {}

    timeout = int(b.get("timeout_seconds", 10))
    max_bytes = int(b.get("max_bytes", 200_000))
    allowed_ct = [c.lower() for c in (b.get("allowed_content_types") or [])]
    max_redirects = int(b.get("max_redirects", 3))

    cur = _normalize_url(url)
    redirects = 0

    opener = urllib.request.build_opener(_NoRedirect)

    while True:
        _validate_target(cur)

        req = urllib.request.Request(
            cur,
            headers={
                "User-Agent": "CortexEngine/0.1 (SAFE browser.fetch)",
                "Accept": ", ".join(allowed_ct) if allowed_ct else "*/*",
            },
            method="GET",
        )

        try:
            resp = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            # Manual redirects
            if e.code in (301, 302, 303, 307, 308):
                loc = e.headers.get("Location")
                if not loc:
                    raise BrowserBlocked("Redirect without Location header")

                redirects += 1
                if redirects > max_redirects:
                    raise BrowserBlocked("Too many redirects")

                cur = urllib.parse.urljoin(cur, loc)
                continue
            raise

        status = getattr(resp, "status", 200)
        ct = (resp.headers.get("Content-Type")
              or "").split(";")[0].strip().lower()

        if allowed_ct and ct not in allowed_ct:
            raise BrowserBlocked(f"Blocked content-type: {ct or '(missing)'}")

        data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise BrowserBlocked(f"Response too large (>{max_bytes} bytes)")

        text = data.decode("utf-8", errors="replace")

        return {
            "url": cur,
            "status": status,
            "content_type": ct,
            "bytes": len(data),
            "text": text,
        }


def _normalize_browser_name(browser: str) -> str:
    b = (browser or "default").strip().lower()
    aliases = {
        "google chrome": "chrome",
        "chrome": "chrome",
        "microsoft edge": "edge",
        "edge": "edge",
        "brave": "brave",
        "brave browser": "brave",
        "firefox": "firefox",
        "mozilla firefox": "firefox",
        "default": "default",
        "system": "default",
    }
    return aliases.get(b, b)


def _find_browser_exe_windows(browser: str) -> str | None:
    b = browser

    # 1) PATH first
    names = {
        "chrome": ["chrome.exe", "chrome"],
        "edge": ["msedge.exe", "msedge"],
        "brave": ["brave.exe", "brave"],
        "firefox": ["firefox.exe", "firefox"],
    }.get(b, [])

    for n in names:
        p = shutil.which(n)
        if p:
            return p

    # 2) Common install locations
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get(
        "ProgramFiles(x86)", r"C:\Program Files (x86)")

    candidates: list[str] = []
    if b == "chrome":
        candidates += [
            str(Path(program_files) / "Google/Chrome/Application/chrome.exe"),
            str(Path(program_files_x86) / "Google/Chrome/Application/chrome.exe"),
            str(Path(local) / "Google/Chrome/Application/chrome.exe"),
        ]
    elif b == "edge":
        candidates += [
            str(Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe"),
            str(Path(program_files) / "Microsoft/Edge/Application/msedge.exe"),
            str(Path(local) / "Microsoft/Edge/Application/msedge.exe"),
        ]
    elif b == "brave":
        candidates += [
            str(Path(program_files) /
                "BraveSoftware/Brave-Browser/Application/brave.exe"),
            str(Path(program_files_x86) /
                "BraveSoftware/Brave-Browser/Application/brave.exe"),
            str(Path(local) / "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ]
    elif b == "firefox":
        candidates += [
            str(Path(program_files) / "Mozilla Firefox/firefox.exe"),
            str(Path(program_files_x86) / "Mozilla Firefox/firefox.exe"),
            str(Path(local) / "Mozilla Firefox/firefox.exe"),
        ]

    for c in candidates:
        if c and Path(c).exists():
            return c

    return None


def _find_browser_exe_linux(browser: str) -> str | None:
    # Try common binary names (PATH)
    names = {
        "chrome": ["google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser"],
        "edge": ["microsoft-edge", "microsoft-edge-stable", "msedge"],
        "brave": ["brave-browser", "brave"],
        "firefox": ["firefox"],
    }.get(browser, [])

    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _open_on_macos(url: str, browser: str) -> dict:
    # macOS uses app bundle names with: open -a "App Name" URL
    app_map = {
        "chrome": "Google Chrome",
        "edge": "Microsoft Edge",
        "brave": "Brave Browser",
        "firefox": "Firefox",
    }
    app = app_map.get(browser)
    if not app:
        raise BrowserBlocked(f"Unsupported browser: {browser}")

    # open returns immediately; if app isn't installed, macOS returns non-zero
    try:
        subprocess.run(["open", "-a", app, url], check=True)
    except subprocess.CalledProcessError:
        raise BrowserBlocked(
            f"{browser} browser not found on system (macOS app '{app}' not available)")
    return {"opened": True, "url": url, "browser": browser, "method": f"open -a {app}"}


def fsafe_browser_open(url: str, browser: str = "default") -> dict:
    """
    SAFE tool: open URL in a specific browser or default browser.
    Cross-platform: Windows/macOS/Linux.
    Still enforces _validate_target (blocks localhost/private IP).
    """
    cur = _normalize_url(url)
    _validate_target(cur)

    b = _normalize_browser_name(browser)

    # Default/system browser
    if b == "default":
        ok = webbrowser.open(cur, new=2, autoraise=True)
        return {"opened": ok, "url": cur, "browser": "default"}

    if b not in {"chrome", "edge", "brave", "firefox"}:
        raise BrowserBlocked(f"Unsupported browser: {browser}")

    system = platform.system().lower()

    # macOS
    if system == "darwin":
        return _open_on_macos(cur, b)

    # Windows
    if system == "windows":
        exe = _find_browser_exe_windows(b)
        if not exe:
            raise BrowserBlocked(f"{b} browser not found on system")
        subprocess.Popen([exe, cur], close_fds=True)
        return {"opened": True, "url": cur, "browser": b, "exe": exe}

    # Linux (and others): try binary
    exe = _find_browser_exe_linux(b)
    if exe:
        subprocess.Popen([exe, cur], close_fds=True)
        return {"opened": True, "url": cur, "browser": b, "exe": exe}

    # Fallback: xdg-open only opens default browser (not specific)
    xdg = shutil.which("xdg-open")
    if xdg:
        # We can't guarantee specific browser here
        subprocess.Popen([xdg, cur], close_fds=True)
        return {"opened": True, "url": cur, "browser": b, "exe": None, "note": "Opened via xdg-open (default browser fallback)"}

    raise BrowserBlocked(f"{b} browser not found on system")


def _make_site_search_url(site: str, query: str) -> str:
    s = (site or "").strip().lower()
    q = urllib.parse.quote_plus((query or "").strip())

    # Normalize site input like "youtube.com" / "www.youtube.com"
    if s.startswith("www."):
        s = s[4:]

    if "youtube" in s:
        return f"https://www.youtube.com/results?search_query={q}"

    if "linkedin" in s:
        # People search (deterministic; no guessing profile slugs)
        return f"https://www.linkedin.com/search/results/people/?keywords={q}"

    if "google" in s:
        return f"https://www.google.com/search?q={q}"

    # Generic fallback: DuckDuckGo site search
    # e.g. site:example.com query
    site_q = urllib.parse.quote_plus(s) if s else ""
    if site_q:
        return f"https://duckduckgo.com/?q=site%3A{site_q}+{q}"
    return f"https://duckduckgo.com/?q={q}"


def fsafe_browser_search(query: str, site: str = "google.com", browser: str = "default") -> dict:
    """
    SAFE tool: open a search results page for the given query on the target site.
    Deterministic: does not fetch page HTML.
    """
    if not query or not str(query).strip():
        raise ValueError("query is required")

    url = _make_site_search_url(site=site, query=query)
    out = fsafe_browser_open(url=url, browser=browser)
    return {
        "opened": out.get("opened", False),
        "url": url,
        "browser": out.get("browser", browser),
        "site": site,
        "query": query,
    }
