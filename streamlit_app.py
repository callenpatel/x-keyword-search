"""X Keyword Search — web version.

Watches one X List and shows every post that mentions your keywords.
Open the URL and the latest matches are already on screen: no install, no sign-in.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

import scanner
from scanner import (
    DEFAULT_LOOKBACK,
    EMAIL_FORMATS,
    LOOKBACK_CHOICES,
    PageProblem,
    build_csv,
    compile_keywords,
    fmt_time,
    list_id_from,
)

CHECK_EVERY_MINUTES = 15
DATA_DIR = Path(os.environ.get("XKS_DATA_DIR", ".data"))
RESULTS_FILE = DATA_DIR / "results.json"

st.set_page_config(page_title="X Keyword Search", page_icon="🔎", layout="wide")


# --------------------------------------------------------------------------- config

def _load_secrets_into_env() -> None:
    """Streamlit secrets -> environment, so scanner.py never imports streamlit."""
    try:
        for k in ("TWITTERAPI_IO_KEY", "SENDER_EMAIL", "SENDER_APP_PASSWORD",
                  "SMTP_HOST", "SMTP_PORT", "DEFAULT_LIST_URL", "DEFAULT_KEYWORDS"):
            if k in st.secrets and not os.environ.get(k):
                os.environ[k] = str(st.secrets[k])
    except Exception:
        pass  # no secrets.toml locally; environment variables still work


_load_secrets_into_env()

# Shipped defaults, so the app is useful the second it loads with nothing typed in.
DEFAULT_LIST_URL = (os.environ.get("DEFAULT_LIST_URL") or "").strip()
DEFAULT_KEYWORDS = (os.environ.get("DEFAULT_KEYWORDS") or "").strip().replace("\\n", "\n")


# --------------------------------------------------------------------------- state

def _load_results() -> list[dict]:
    try:
        return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_results(results: list[dict]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RESULTS_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # hosted disks are temporary; the table still works from session state


if "results" not in st.session_state:
    st.session_state.results = _load_results()
    st.session_state.seen_ids = {r["id"] for r in st.session_state.results}
    st.session_state.status = ""
    st.session_state.last_auto = 0.0
    st.session_state.first_load_done = False


@st.cache_data(ttl=CHECK_EVERY_MINUTES * 60, show_spinner=False)
def _read_list_cached(list_id: str, lookback_days: float) -> list[dict]:
    """One API read is shared by everyone who opens the app within the TTL.

    This is the spend cap: ten people opening the link in the same 15 minutes
    costs the same as one.
    """
    return scanner.read_list(list_id, None, lookback_days)


def run_check(list_link: str, keywords_raw: str, lookback_label: str, quiet: bool = False) -> None:
    list_id = list_id_from(list_link)
    if not list_id:
        if not quiet:
            st.session_state.status = (
                "Paste the List link first — it looks like https://x.com/i/lists/1234567890123456789"
            )
        return
    keywords = compile_keywords(keywords_raw)
    if not keywords:
        if not quiet:
            st.session_state.status = "Type at least one keyword, one per line."
        return
    try:
        with st.spinner("Reading the List..."):
            posts = _read_list_cached(list_id, LOOKBACK_CHOICES.get(lookback_label, 2))
    except PageProblem as e:
        st.session_state.status = f"Last check failed: {e}"
        return
    except Exception as e:
        st.session_state.status = f"Could not read the List. {e.__class__.__name__}: {e}"
        return

    new = 0
    for p in posts:
        if p["id"] in st.session_state.seen_ids:
            continue
        kws = scanner.find_matches(
            p["text"] + "\n" + p.get("quoted", "") + "\n" + p.get("name", ""), keywords
        )
        if kws:
            row = dict(p, keywords=kws, emailed=False)
            st.session_state.results.append(row)
            st.session_state.seen_ids.add(p["id"])
            new += 1
    _save_results(st.session_state.results)
    now = datetime.now().strftime("%I:%M %p").lstrip("0")
    st.session_state.status = (
        f"Checked at {now}: read {len(posts)} posts from the last {lookback_label}, "
        f"{new} new match{'es' if new != 1 else ''}. "
        f"{len(st.session_state.results)} matches total."
    )


def send_summary(to: str, fmt: str, list_link: str, only_unsent: bool) -> None:
    items = sorted(st.session_state.results, key=lambda x: x.get("time", ""), reverse=True)
    if only_unsent:
        items = [r for r in items if not r.get("emailed")]
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        items = [r for r in items if r.get("time", "") >= cutoff] or items[:50]
    if not items:
        st.session_state.status = "Nothing to email yet."
        return
    try:
        with st.spinner(f"Emailing {len(items)} matches to {to}..."):
            scanner.send_email(to, items, fmt, list_link)
    except Exception as e:
        st.session_state.status = f"Email failed: {e}"
        return
    for r in items:
        r["emailed"] = True
    _save_results(st.session_state.results)
    st.session_state.status = (
        f"Emailed {len(items)} match{'es' if len(items) != 1 else ''} to {to} at "
        f"{datetime.now().strftime('%I:%M %p').lstrip('0')}."
    )


# --------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.subheader("What to watch")
    list_link = st.text_input(
        "X List link",
        value=DEFAULT_LIST_URL,
        key="list_link",
        placeholder="https://x.com/i/lists/1234567890",
        help="Open the List on x.com and paste the address.",
    )
    keywords_raw = st.text_area(
        "Keywords, one per line",
        value=DEFAULT_KEYWORDS,
        key="keywords_raw",
        height=160,
        help="A line can be a name or a phrase. Matching is whole-word and ignores capitals, "
             'so "ICE" will not match "service".',
    )
    lookback = st.selectbox(
        "Each check looks back",
        list(LOOKBACK_CHOICES),
        index=list(LOOKBACK_CHOICES).index(DEFAULT_LOOKBACK),
        key="lookback",
    )
    check_clicked = st.button("Check now", type="primary", width="stretch")
    st.checkbox(f"Keep checking every {CHECK_EVERY_MINUTES} minutes", key="auto", value=True)
    st.caption("Automatic checks run while this tab is open.")

    st.divider()
    st.subheader("Email me")
    if not scanner.email_ready():
        st.caption("Email sending is not configured for this app.")
        email_to, email_fmt, send_clicked = "", EMAIL_FORMATS[0], False
    else:
        email_to = st.text_input("Your email address", key="email_to", placeholder="you@example.com")
        email_fmt = st.radio("Format", EMAIL_FORMATS, key="email_fmt")
        send_clicked = st.button("Send me a summary now", width="stretch")
        st.checkbox("Also email after each check that finds something new", key="email_on_check")

# --------------------------------------------------------------------------- main

st.title("X Keyword Search")
st.caption("Watches one X List and shows every post that mentions your keywords.")

# First visit: check straight away so the table is populated before anyone clicks anything.
if not st.session_state.first_load_done:
    st.session_state.first_load_done = True
    st.session_state.last_auto = time.time()
    run_check(list_link, keywords_raw, lookback, quiet=True)

if check_clicked:
    run_check(list_link, keywords_raw, lookback)
    if st.session_state.get("email_on_check") and email_to:
        send_summary(email_to, email_fmt, list_link, only_unsent=True)

if scanner.email_ready() and send_clicked:
    if not email_to:
        st.session_state.status = "Type your email address first."
    else:
        send_summary(email_to, email_fmt, list_link, only_unsent=False)


@st.fragment(run_every=60 if st.session_state.get("auto") else None)
def results_panel() -> None:
    if st.session_state.get("auto"):
        elapsed = time.time() - st.session_state.last_auto
        if elapsed >= CHECK_EVERY_MINUTES * 60 and list_id_from(st.session_state.get("list_link", "")):
            st.session_state.last_auto = time.time()
            run_check(
                st.session_state.get("list_link", ""),
                st.session_state.get("keywords_raw", ""),
                st.session_state.get("lookback", DEFAULT_LOOKBACK),
                quiet=True,
            )

    if st.session_state.status:
        st.info(st.session_state.status)

    results = sorted(st.session_state.results, key=lambda x: x.get("time", ""), reverse=True)
    n = len(results)
    head, dl = st.columns([4, 1])
    head.subheader(f"{n} match{'es' if n != 1 else ''} found so far")
    if results:
        dl.download_button(
            "Download spreadsheet",
            data=("﻿" + build_csv(results)).encode("utf-8"),
            file_name=f"x-keyword-matches-{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
            width="stretch",
        )

    if not results:
        st.write("No matches yet. Add a List link and keywords in the sidebar, then click Check now.")
        return

    df = pd.DataFrame([
        {
            "When": fmt_time(r.get("time", "")),
            "Who": f"{r.get('name', '')}  @{r.get('handle', '')}",
            "Keyword": ", ".join(r.get("keywords", [])),
            "Post": (r.get("text", "") or "").replace("\n", " "),
            "Link": r.get("url", ""),
        }
        for r in results
    ])
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        height=560,
        column_config={
            "When": st.column_config.TextColumn(width="small"),
            "Who": st.column_config.TextColumn(width="medium"),
            "Keyword": st.column_config.TextColumn(width="small"),
            "Post": st.column_config.TextColumn(width="large"),
            "Link": st.column_config.LinkColumn("Open", display_text="Open on X", width="small"),
        },
    )


results_panel()
