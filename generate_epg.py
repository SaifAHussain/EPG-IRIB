#!/usr/bin/env python3
"""
IRIB EPG Generator
Fetches IRIB Quran and Radio Quran schedules from the Sepehr API
and outputs a single XMLTV epg.xml.
Designed to run via GitHub Actions on a schedule — set it and forget it.

OAuth 1.0 signatures are generated fresh per-request using credentials
stored as GitHub Secrets (or env vars for local runs).
"""

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from xml.dom import minidom
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from requests_oauthlib import OAuth1Session

# ─── Config ──────────────────────────────────────────────────────────────────

IRAN_TZ = ZoneInfo("Asia/Tehran")

# IRIB channels: channel_id -> (tvg_id, display_name, logo_url)
CHANNELS = {
    46: (
        "QuranTV.ir@SD",
        "IRIB Quran",
        "https://lb-cdn.sepehrtv.ir/img/channel/quarnlogo.png",
    ),
    15741: (
        "Radio Quran",
        "Radio Quran",
        "https://logoyab.com/wp-content/uploads/2024/08/Radio-Quran-Logo.png",
    ),
}

# OAuth 1.0 credentials — set via env vars (or GitHub Secrets → workflow env).
# To find fresh credentials: visit sepehrtv.ir, open DevTools → Sources,
# search JS for "getAuthHeaderForRequest" or "consumer" to extract the keys.
CONSUMER_KEY = os.environ.get("SEPEHR_CONSUMER_KEY", "")
CONSUMER_SECRET = os.environ.get("SEPEHR_CONSUMER_SECRET", "")
ACCESS_TOKEN = os.environ.get("SEPEHR_ACCESS_TOKEN", "")
TOKEN_SECRET = os.environ.get("SEPEHR_TOKEN_SECRET", "")

if not all([CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, TOKEN_SECRET]):
    print("⚠️  OAuth credentials not fully set — IRIB EPG will be empty.")
    print("   Required env vars: SEPEHR_CONSUMER_KEY, SEPEHR_CONSUMER_SECRET,")
    print("                      SEPEHR_ACCESS_TOKEN, SEPEHR_TOKEN_SECRET")

API_BASE = "https://sepehrapi.sepehrtv.ir/v3/epg/tvprogram"

DAYS_TO_FETCH = 1
OUTPUT_FILE = "epg.xml"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


# ─── OAuth Session ───────────────────────────────────────────────────────────


def create_session() -> OAuth1Session:
    """Create an OAuth 1.0 session that signs every request automatically."""
    session = OAuth1Session(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=TOKEN_SECRET,
        signature_method="HMAC-SHA1",
    )
    session.headers.update(
        {
            "Accept": "*/*",
            "Origin": "https://sepehrtv.ir",
            "Referer": "https://sepehrtv.ir/",
            "User-Agent": USER_AGENT,
        }
    )
    return session


# ─── Helpers ─────────────────────────────────────────────────────────────────


def fetch_epg(session: OAuth1Session, channel_id: int, date: datetime) -> list:
    """Fetch one day of EPG from the Sepehr API."""
    params = {
        "channel_id": channel_id,
        "date": f"{date.year}-{date.month}-{date.day}",
    }
    resp = session.get(API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("list", [])


def check_token(session: OAuth1Session) -> bool:
    """Quick health-check for the OAuth credentials."""
    try:
        progs = fetch_epg(session, 46, datetime.now(IRAN_TZ))
        return len(progs) > 0
    except Exception:
        return False


def ms_to_xmltv(ms: int) -> str:
    """Convert millisecond timestamp to XMLTV datetime (Iran TZ)."""
    dt = datetime.fromtimestamp(ms / 1000, tz=IRAN_TZ)
    return dt.strftime("%Y%m%d%H%M%S %z")


def pretty_xml(root: ET.Element) -> str:
    """Produce a nicely indented XML string with proper declaration."""
    raw = ET.tostring(root, encoding="unicode")
    dom = minidom.parseString(raw)
    pretty = dom.toprettyxml(indent="  ")
    lines = pretty.split("\n")
    if lines and lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print("🕌 IRIB EPG Generator")
    print("=" * 50)

    session = create_session()

    tv = ET.Element("tv")
    tv.set("generator-info-name", "EPG-IRIB")
    tv.set("generator-info-url", "https://github.com/SaifAHussain/EPG-IRIB")

    # Token check
    if not check_token(session):
        print("❌  OAuth credentials failed — EPG will be empty this run.")
        print("   Sepehr may have rotated their app keys.")
        for cid, (tvg_id, name, logo) in CHANNELS.items():
            ch = ET.SubElement(tv, "channel", id=tvg_id)
            ET.SubElement(ch, "display-name", lang="fa").text = name
            if logo:
                ET.SubElement(ch, "icon", src=logo)
        xml_str = pretty_xml(tv)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(xml_str)
        print(f"\n⚠️  Wrote empty {OUTPUT_FILE}")
        sys.exit(1)

    today = datetime.now(IRAN_TZ)
    total = 0

    # Channel definitions
    for cid, (tvg_id, name, logo) in CHANNELS.items():
        ch = ET.SubElement(tv, "channel", id=tvg_id)
        ET.SubElement(ch, "display-name", lang="fa").text = name
        if logo:
            ET.SubElement(ch, "icon", src=logo)

    # Programmes
    for cid, (tvg_id, name, logo) in CHANNELS.items():
        print(f"\n📺 {name} (id={cid})")
        for day_offset in range(DAYS_TO_FETCH):
            date = today + timedelta(days=day_offset)
            try:
                progs = fetch_epg(session, cid, date)
                for p in progs:
                    prog_el = ET.SubElement(
                        tv,
                        "programme",
                        start=ms_to_xmltv(p["start"]),
                        channel=tvg_id,
                    )
                    if p["duration"] > 0:
                        stop_ms = p["start"] + p["duration"] * 60_000
                        prog_el.set("stop", ms_to_xmltv(stop_ms))
                    ET.SubElement(prog_el, "title", lang="fa").text = p["title"]
                    if p.get("descSummary"):
                        ET.SubElement(prog_el, "desc", lang="fa").text = p[
                            "descSummary"
                        ]
                total += len(progs)
                print(f"   {date.strftime('%Y-%m-%d')}: {len(progs)} programmes ✓")
            except Exception as e:
                print(f"   {date.strftime('%Y-%m-%d')}: Error — {e}")

    xml_str = pretty_xml(tv)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"\n✅ {OUTPUT_FILE} written — {total} programmes")
    print(f"   File size: {len(xml_str.encode()):,} bytes")

    if total == 0:
        print("\n⚠️  0 programmes fetched — credentials may be invalid.")
        sys.exit(1)


if __name__ == "__main__":
    main()
