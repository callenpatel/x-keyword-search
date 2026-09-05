"""Core logic for X Keyword Search: keyword matching, reading an X List, email, CSV.

No UI and no secrets in this file. Credentials come from the environment
(or Streamlit secrets, which are loaded into the environment by streamlit_app.py).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- config

API_BASE = "https://api.twitterapi.io"
LOOKBACK_CHOICES = {
    "6 hours": 0.25,
    "12 hours": 0.5,
    "1 day": 1,
    "2 days": 2,
    "3 days": 3,
    "1 week": 7,
    "2 weeks": 14,
}
DEFAULT_LOOKBACK = "2 days"
MAX_PAGES_PER_CHECK = 25  # safety cap (~500 posts) so a busy List cannot run up the bill

EMAIL_FORMATS = ["Readable summary", "Spreadsheet attached"]


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def api_key() -> str:
    return _env("TWITTERAPI_IO_KEY")


def sender_email() -> str:
    return _env("SENDER_EMAIL")


def sender_password() -> str:
    return _env("SENDER_APP_PASSWORD")


def smtp_host() -> str:
    return _env("SMTP_HOST", "smtp.gmail.com")


def smtp_port() -> int:
    try:
        return int(_env("SMTP_PORT", "465"))
    except ValueError:
        return 465


def email_ready() -> bool:
    return bool(sender_email() and sender_password())


class PageProblem(Exception):
    """A problem worth showing to the person using the app, in plain words."""


# --------------------------------------------------------------------------- matching

def _clean(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―−]", "-", s)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).casefold().strip()


def compile_keywords(raw: str) -> list[tuple[str, re.Pattern]]:
    """One keyword or phrase per line (commas also work). Whole-word, case-insensitive."""
    out = []
    for kw in re.split(r"[\n,]", raw or ""):
        kw = kw.strip().lstrip("#@")
        if not kw:
            continue
        parts = [re.escape(p) for p in re.split(r"[\s\-]+", _clean(kw)) if p]
        if not parts:
            continue
        pat = re.compile(r"(?<!\w)" + r"[\s\-]+".join(parts) + r"(?!\w)")
        out.append((kw, pat))
    return out


def find_matches(text: str, keywords: list[tuple[str, re.Pattern]]) -> list[str]:
    cleaned = _clean(text)
    return [kw for kw, pat in keywords if pat.search(cleaned)]


def list_id_from(link: str) -> str | None:
    m = re.search(r"(\d{8,25})", link or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------- reading X

def _api_get(path: str, params: dict) -> dict:
    key = api_key()
    if not key:
        raise PageProblem(
            "No API key is configured for this app. Set TWITTERAPI_IO_KEY in the app's secrets."
        )
    url = f"{API_BASE}{path}?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    req = urllib.request.Request(url, headers={"X-API-Key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        if e.code in (401, 403):
            raise PageProblem("The API key was rejected. Check TWITTERAPI_IO_KEY in the app's secrets.")
        if e.code == 402:
            raise PageProblem("The API account has run out of credit. Top it up at twitterapi.io.")
        if e.code == 429:
            raise PageProblem(
                "The API refused the request (HTTP 429). Usually this means the account is out of credit "
                "or too many requests were made. Wait a few minutes and try again.\n\nServer said: "
                + (body or "(nothing)")
            )
        raise PageProblem(f"The API returned an error (HTTP {e.code}). {body}")
    except urllib.error.URLError as e:
        raise PageProblem(f"Could not reach the API ({e.reason}). Try again in a moment.")


def _parse_time(s: str) -> str:
    """Return ISO-8601 UTC for whatever date format the API used."""
    if not s:
        return ""
    for fmt, assume_utc in (
        ("%a %b %d %H:%M:%S %z %Y", False),
        ("%Y-%m-%dT%H:%M:%S.%fZ", True),
        ("%Y-%m-%dT%H:%M:%SZ", True),
    ):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if assume_utc:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return s


def _to_post(t: dict) -> dict | None:
    pid = str(t.get("id") or t.get("id_str") or t.get("tweet_id") or "")
    if not pid.isdigit():
        return None
    author = t.get("author") or t.get("user") or {}
    handle = author.get("userName") or author.get("screen_name") or author.get("username") or ""
    name = author.get("name") or handle
    text = t.get("text") or t.get("full_text") or ""
    quoted = t.get("quoted_tweet") or t.get("quoted_status") or {}
    quoted_text = (quoted.get("text") or quoted.get("full_text") or "") if isinstance(quoted, dict) else ""
    rt = t.get("retweeted_tweet") or t.get("retweeted_status") or {}
    if isinstance(rt, dict) and (rt.get("text") or rt.get("full_text")):
        text = text or ("RT " + (rt.get("text") or rt.get("full_text")))
    return {
        "id": pid,
        "handle": handle,
        "name": name,
        "time": _parse_time(t.get("createdAt") or t.get("created_at") or ""),
        "text": text,
        "quoted": quoted_text,
        "url": t.get("url") or t.get("twitterUrl") or f"https://x.com/{handle or 'i'}/status/{pid}",
    }


def read_list(list_id: str, status=None, lookback_days: float = 2) -> list[dict]:
    """Read the List through the API, newest first, going back `lookback_days` and no further."""
    say = status or (lambda _msg: None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    posts: dict[str, dict] = {}
    page = 0
    reached_old = False
    cursor = ""
    for page in range(MAX_PAGES_PER_CHECK):
        say(f"Reading the List... (page {page + 1})")
        data = _api_get("/twitter/list/tweets", {"listId": list_id, "cursor": cursor})
        if isinstance(data, dict) and data.get("status") == "error":
            raise PageProblem(f"The API reported a problem: {data.get('msg') or data.get('message') or data}")
        tweets = data.get("tweets") if isinstance(data, dict) else None
        if tweets is None and isinstance(data, dict):
            tweets = data.get("data") if isinstance(data.get("data"), list) else (data.get("data") or {}).get("tweets")
        if not isinstance(tweets, list):
            raise PageProblem(
                "The API answered in an unexpected format.\n\n" + json.dumps(data)[:300]
            )
        reached_old = False
        for t in tweets:
            p = _to_post(t)
            if not p:
                continue
            if p["time"] and p["time"] < cutoff:
                reached_old = True
                continue
            posts.setdefault(p["id"], p)
        if reached_old or not data.get("has_next_page") or not data.get("next_cursor"):
            break
        cursor = data["next_cursor"]
        time.sleep(1)
    if not posts and page == 0 and not reached_old:
        raise PageProblem(
            "No posts came back for this List. Check that the List link is right and that the List is public."
        )
    return sorted(posts.values(), key=lambda x: int(x["id"]))


def scan(list_id: str, keywords, lookback_days: float, seen_ids: set[str], status=None) -> tuple[list[dict], int]:
    """Read the List and return (new matches, number of posts read)."""
    posts = read_list(list_id, status, lookback_days)
    new: list[dict] = []
    for p in posts:
        if p["id"] in seen_ids:
            continue
        kws = find_matches(p["text"] + "\n" + p.get("quoted", "") + "\n" + p.get("name", ""), keywords)
        if kws:
            p["keywords"] = kws
            p["emailed"] = False
            new.append(p)
    return new, len(posts)


# --------------------------------------------------------------------------- formatting

def fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%b %d %I:%M %p").replace(" 0", " ")
    except Exception:
        return (iso or "")[:16]


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_summary_html(matches: list[dict], list_url: str, window: str = "") -> str:
    rows = []
    for r in matches:
        rows.append(
            "<tr>"
            f"<td style='white-space:nowrap;color:#555'>{_html_escape(fmt_time(r.get('time', '')))}</td>"
            f"<td><b>{_html_escape(r.get('name', ''))}</b><br>"
            f"<span style='color:#777'>@{_html_escape(r.get('handle', ''))}</span></td>"
            f"<td>{_html_escape(', '.join(r.get('keywords', [])))}</td>"
            f"<td>{_html_escape(r.get('text', ''))}<br>"
            f"<a href='{_html_escape(r.get('url', ''))}'>Open post</a></td>"
            "</tr>"
        )
    body = "".join(rows) if rows else "<tr><td colspan='4'>No new matches.</td></tr>"
    return (
        "<html><body style='font-family:Helvetica,Arial,sans-serif;font-size:14px;color:#222'>"
        "<h2 style='margin-bottom:4px'>X keyword matches</h2>"
        f"<p style='color:#666;margin-top:0'>{len(matches)} match{'es' if len(matches) != 1 else ''}"
        f"{' from the last ' + _html_escape(window) if window else ''} "
        f"&middot; <a href='{_html_escape(list_url)}'>the List</a></p>"
        "<table cellpadding='8' cellspacing='0' style='border-collapse:collapse;border:1px solid #ddd'>"
        "<tr style='background:#f3f4f6'><th align='left'>When</th><th align='left'>Who</th>"
        "<th align='left'>Keyword</th><th align='left'>Post</th></tr>"
        f"{body}</table></body></html>"
    )


def build_csv(matches: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["When", "Name", "Handle", "Keywords", "Post", "Link"])
    for r in matches:
        w.writerow([
            fmt_time(r.get("time", "")),
            r.get("name", ""),
            r.get("handle", ""),
            ", ".join(r.get("keywords", [])),
            r.get("text", ""),
            r.get("url", ""),
        ])
    return buf.getvalue()


# --------------------------------------------------------------------------- email

def send_email(to: str, matches: list[dict], fmt: str, list_url: str, window: str = "") -> None:
    """Send the summary. Raises with a readable message on failure."""
    import smtplib
    from email.message import EmailMessage

    if not email_ready():
        raise RuntimeError("No sending email account is configured for this app.")
    n = len(matches)
    msg = EmailMessage()
    suffix = f" in the last {window}" if window else ""
    msg["Subject"] = f"X keyword matches: {n} new{suffix}" if n else f"X keyword matches: nothing new{suffix}"
    msg["From"] = sender_email()
    msg["To"] = to
    lines = [
        f"{fmt_time(r.get('time', ''))} | @{r.get('handle', '')} | {', '.join(r.get('keywords', []))} | "
        f"{r.get('text', '')} | {r.get('url', '')}"
        for r in matches
    ]
    msg.set_content(f"{n} new match(es).\n\n" + "\n\n".join(lines) if lines else "No new matches.")
    if fmt == EMAIL_FORMATS[1]:
        msg.add_alternative(
            f"<html><body><p>{n} new match(es). The spreadsheet is attached.</p></body></html>",
            subtype="html",
        )
        msg.add_attachment(
            ("﻿" + build_csv(matches)).encode("utf-8"),
            maintype="text",
            subtype="csv",
            filename=f"x-keyword-matches-{datetime.now().strftime('%Y-%m-%d')}.csv",
        )
    else:
        msg.add_alternative(build_summary_html(matches, list_url, window), subtype="html")
    with smtplib.SMTP_SSL(smtp_host(), smtp_port(), timeout=45) as s:
        s.login(sender_email(), sender_password().replace(" ", ""))
        s.send_message(msg)
