#!/usr/bin/env python3
"""
IRIB EPG Generator
Fetches IRIB Quran TV schedule from the Sepehr API (OAuth 1.0) and
Radio Quran schedule from radioquran.ir HTML page (public, no auth needed).
Outputs a single XMLTV epg.xml.

Designed to run via GitHub Actions on a schedule — set it and forget it.
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from xml.dom import minidom
from zoneinfo import ZoneInfo

from curl_cffi import requests as cffi_requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

load_dotenv()

# ─── Config ──────────────────────────────────────────────────────────────────

IRAN_TZ = ZoneInfo("Asia/Tehran")

# Sepehr TV channels: channel_id -> (tvg_id, display_name, logo_url)
SEPEHR_CHANNELS = {
    46: (
        "QuranTV.ir@SD",
        "IRIB Quran",
        "https://lb-cdn.sepehrtv.ir/img/channel/quarnlogo.png",
    ),
}

# Radio Quran — sourced from radioquran.ir (no auth required)
RADIO_QURAN = {
    "tvg_id": "Radio Quran",
    "display_name": "Radio Quran",
    "logo": "https://logoyab.com/wp-content/uploads/2024/08/Radio-Quran-Logo.png",
    "html_url": "https://radioquran.ir/ChannelConductor/",
    "json_url": "https://radioquran.ir/jsonfeeders/epg/",
}

# OAuth 1.0 credentials for Sepehr — set via env vars (or GitHub Secrets).
CONSUMER_KEY = os.environ.get("SEPEHR_CONSUMER_KEY", "")
CONSUMER_SECRET = os.environ.get("SEPEHR_CONSUMER_SECRET", "")
ACCESS_TOKEN = os.environ.get("SEPEHR_ACCESS_TOKEN", "")
TOKEN_SECRET = os.environ.get("SEPEHR_TOKEN_SECRET", "")

SEPEHR_API_BASE = "https://sepehrapi.sepehrtv.ir/v3/epg/tvprogram"

OUTPUT_FILE = "epg.xml"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ─── OAuth Session (Sepehr) ─────────────────────────────────────────────────


def create_sepehr_session() -> OAuth1Session | None:
    """Create an OAuth 1.0 session for Sepehr. Returns None if creds missing."""
    if not all([CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, TOKEN_SECRET]):
        return None
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


# ─── Sepehr helpers ──────────────────────────────────────────────────────────


def fetch_sepehr_epg(session: OAuth1Session, channel_id: int, date: datetime) -> list:
    """Fetch one day of EPG from the Sepehr API."""
    params = {
        "channel_id": channel_id,
        "date": date.strftime("%Y-%m-%d"),
    }
    resp = session.get(SEPEHR_API_BASE, params=params, timeout=30)
    if resp.status_code == 500:
        # The API returns 500 for dates that have no data yet — not a real error.
        return []
    resp.raise_for_status()
    return resp.json().get("list", [])


def check_sepehr_token(session: OAuth1Session) -> bool:
    """Quick health-check for the OAuth credentials."""
    try:
        progs = fetch_sepehr_epg(session, 46, datetime.now(IRAN_TZ))
        return len(progs) > 0
    except Exception:
        return False


def ms_to_xmltv(ms: int) -> str:
    """Convert millisecond timestamp to XMLTV datetime (Iran TZ)."""
    dt = datetime.fromtimestamp(ms / 1000, tz=IRAN_TZ)
    return dt.strftime("%Y%m%d%H%M%S %z")


def sepehr_programmes_to_xmltv(
    tv: ET.Element,
    programmes: list[dict],
    tvg_id: str,
) -> int:
    """
    Add Sepehr programmes (one day) to the XMLTV tree.
    Returns number of programmes added.

    Sepehr API item schema:
        id, seriesId, start (ms), duration (minutes), channelId,
        barred, recordable, ageRating, title, descSummary, descFull,
        imageUrl, current, state, media{id, preview, teams, streams, logo}
    """
    count = 0
    for prog in programmes:
        start_ms = prog.get("start")
        title = prog.get("title", "").strip()
        if not start_ms or not title:
            continue

        attrs = {"start": ms_to_xmltv(start_ms), "channel": tvg_id}

        # Compute stop from start + duration (duration is in minutes)
        duration_min = prog.get("duration", 0)
        if duration_min and duration_min > 0:
            end_ms = start_ms + duration_min * 60 * 1000
            attrs["stop"] = ms_to_xmltv(end_ms)

        prog_el = ET.SubElement(tv, "programme", **attrs)
        ET.SubElement(prog_el, "title", lang="fa").text = title

        # Description: prefer descFull, fall back to descSummary
        desc = (prog.get("descFull") or prog.get("descSummary") or "").strip()
        if desc:
            ET.SubElement(prog_el, "desc", lang="fa").text = desc

        image = prog.get("imageUrl")
        if image:
            ET.SubElement(prog_el, "icon", src=image)

        count += 1
    return count


# ─── Radio Quran (radioquran.ir) helpers ─────────────────────────────────────


def _cffi_fetch(url: str, max_retries: int = 3, timeout: int = 30) -> str | None:
    """
    Fetch a URL using curl_cffi with browser TLS impersonation.

    radioquran.ir blocks/throttles Python's standard `requests` library
    (likely via TLS/JA3 fingerprinting).  curl_cffi uses libcurl's TLS
    stack and can impersonate real browser fingerprints, so the server
    treats it like a normal browser visit.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = cffi_requests.get(
                url,
                impersonate="chrome",
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < max_retries:
                print(f"   ⚠️  Attempt {attempt} failed ({e}), retrying...")
            else:
                print(f"   ⚠️  Failed to fetch {url} after {max_retries} attempts: {e}")
    return None


def fetch_radio_quran_html(max_retries: int = 3) -> str | None:
    """
    Fetch today's schedule HTML from radioquran.ir/ChannelConductor/.
    Returns the raw HTML string, or None on failure.

    The HTML page contains richer data than the JSON feed:
    - Programme descriptions (itemprop="description")
    - Explicit durations in minutes (مدت:X دقیقه)
    - Properly zero-padded times (HH:MM)
    """
    return _cffi_fetch(RADIO_QURAN["html_url"], max_retries=max_retries, timeout=30)


def parse_radio_quran_html(html: str) -> list[dict]:
    """
    Parse the ChannelConductor HTML page into a list of programme dicts.

    Each programme block in the HTML contains:
      - Time:        <div class="fontsize-3">  HH:MM  </div>
      - Title:       <h4 ... itemprop="name ">TITLE</h4>
      - Description: <p ... itemprop="description">DESC</p>
      - Duration:    مدت:X دقیقه
      - Image:       <img class="lazy" ... src="URL" ...>

    Returns list of dicts with keys: time, title, description, duration, image
    """
    times = re.findall(r'fontsize-3">\s*(\d{1,2}:\d{2})\s*</div>', html)
    titles = re.findall(r'itemprop="name ">(.*?)</h4>', html, re.DOTALL)
    descs = re.findall(r'itemprop="description">(.*?)</p>', html, re.DOTALL)
    durations = re.findall(r"مدت:(\d+)\s*دقیقه", html)
    images = re.findall(r'img class="lazy" alt="[^"]*" src="([^"]+)"', html)

    # All lists should be the same length; use the minimum to be safe
    n = min(len(times), len(titles), len(descs), len(durations), len(images))
    if n == 0:
        print(
            f"   Regex found: times={len(times)}, titles={len(titles)}, "
            f"descs={len(descs)}, durations={len(durations)}, images={len(images)} "
            f"(HTML was {len(html)} chars)"
        )
        return []

    programmes = []
    for i in range(n):
        # Clean description: strip whitespace and convert <br> tags to newlines
        desc = descs[i].strip()
        desc = re.sub(r"<br\s*/?>", "\n", desc)
        desc = re.sub(r"<[^>]+>", "", desc)  # strip any remaining HTML tags
        desc = desc.strip()

        programmes.append(
            {
                "time": times[i].strip(),
                "title": titles[i].strip(),
                "description": desc,
                "duration": int(durations[i]),
                "image": images[i],
            }
        )

    return programmes


def fetch_radio_quran_json(max_retries: int = 3) -> list[dict] | None:
    """
    Fallback: fetch today's schedule from the radioquran.ir JSON feed.
    Returns a list of programme dicts (same schema as parse_radio_quran_html),
    or None on failure.

    Note: JSON feed lacks descriptions and durations (always empty).
    """
    raw = _cffi_fetch(RADIO_QURAN["json_url"], max_retries=max_retries, timeout=30)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"   ⚠️  JSON decode error: {e}")
        return None

    containers = data.get("Containers", [])
    if not containers:
        return []
    boxes = containers[0].get("boxes", [])
    # Normalize to the same dict schema as the HTML parser
    programmes = []
    for box in boxes:
        title = box.get("title", "").strip()
        if not title:
            continue
        time_str = box.get("time", "")
        if ":" not in time_str:
            continue
        # Zero-pad the time for consistency
        parts = time_str.strip().split(":")
        try:
            h, m = int(parts[0]), int(parts[1])
            padded_time = f"{h:02d}:{m:02d}"
        except (ValueError, IndexError):
            continue
        image = box.get("image", "")
        if image and not image.startswith("http"):
            image = "https://radioquran.ir" + image
        programmes.append(
            {
                "time": padded_time,
                "title": title,
                "description": "",
                "duration": 0,
                "image": image,
            }
        )
    return programmes


def radio_quran_to_xmltv(
    tv: ET.Element,
    programmes: list[dict],
    tvg_id: str,
    date: datetime,
) -> int:
    """
    Convert Radio Quran programme dicts to XMLTV programme elements.
    Uses the `time` field for start times. Stop times are computed from
    duration when available, otherwise inferred from the next programme.
    Returns count of programmes added.
    """
    # Build a list of (start_dt, title, desc, duration_min, image) tuples
    entries: list[tuple[datetime, str, str, int, str]] = []

    for prog in programmes:
        title = prog.get("title", "").strip()
        if not title:
            continue

        time_str = prog.get("time", "")
        try:
            h, m = time_str.split(":")
            hour, minute = int(h), int(m)
        except (ValueError, AttributeError):
            continue

        start_dt = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        desc = prog.get("description", "")
        duration = prog.get("duration", 0)
        image = prog.get("image", "")

        entries.append((start_dt, title, desc, duration, image))

    # Add to XMLTV tree
    count = 0
    for i, (start_dt, title, desc, duration, image) in enumerate(entries):
        start_str = start_dt.strftime("%Y%m%d%H%M%S %z")

        attrs: dict[str, str] = {"start": start_str, "channel": tvg_id}

        # Compute stop time: prefer explicit duration, fall back to next start
        if duration and duration > 0:
            stop_dt = start_dt + timedelta(minutes=duration)
            attrs["stop"] = stop_dt.strftime("%Y%m%d%H%M%S %z")
        elif i + 1 < len(entries):
            next_start = entries[i + 1][0]
            if next_start > start_dt:
                attrs["stop"] = next_start.strftime("%Y%m%d%H%M%S %z")

        prog_el = ET.SubElement(tv, "programme", **attrs)
        ET.SubElement(prog_el, "title", lang="fa").text = title

        if desc:
            ET.SubElement(prog_el, "desc", lang="fa").text = desc

        if image:
            ET.SubElement(prog_el, "icon", src=image)

        count += 1

    return count


# ─── XML output ──────────────────────────────────────────────────────────────


def prettify_xml(element: ET.Element) -> str:
    """Return a pretty-printed XML string with proper declaration."""
    rough = ET.tostring(element, encoding="unicode", xml_declaration=False)
    parsed = minidom.parseString(rough)
    pretty = parsed.toprettyxml(indent="  ", encoding=None)
    # minidom adds an extra xml declaration — replace with our own
    lines = pretty.splitlines()
    # Drop the minidom declaration line if present
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    # Remove blank lines that minidom sometimes introduces
    lines = [line for line in lines if line.strip()]
    header = '<?xml version="1.0" encoding="UTF-8"?>'
    return header + "\n" + "\n".join(lines) + "\n"


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    now = datetime.now(IRAN_TZ)
    print(f"🕐 EPG generation started at {now.isoformat()}")
    print("   Fetching today's programme data...\n")

    # ── Build the XMLTV root element ─────────────────────────────────────
    tv = ET.Element(
        "tv",
        attrib={
            "generator-info-name": "EPG-IRIB",
            "generator-info-url": "https://github.com/saif-at-github/EPG-IRIB",
        },
    )

    total_programmes = 0
    sepehr_ok = False
    radio_ok = False

    # ── 1. Sepehr TV channels (today only — API has no future data) ──────
    session = create_sepehr_session()
    if session:
        print("🔑 Sepehr OAuth credentials found — checking token...")
        if check_sepehr_token(session):
            print("   ✅ Sepehr token is valid.\n")
            sepehr_ok = True

            # Register Sepehr channel definitions
            for channel_id, (tvg_id, display_name, logo) in SEPEHR_CHANNELS.items():
                ch_el = ET.SubElement(tv, "channel", id=tvg_id)
                ET.SubElement(ch_el, "display-name").text = display_name
                ET.SubElement(ch_el, "icon", src=logo)

            # Fetch programmes for each channel (today only)
            for channel_id, (tvg_id, display_name, _logo) in SEPEHR_CHANNELS.items():
                print(f"📺 {display_name} (Sepehr channel {channel_id}):")
                date_label = now.strftime("%Y-%m-%d")
                try:
                    progs = fetch_sepehr_epg(session, channel_id, now)
                    added = sepehr_programmes_to_xmltv(tv, progs, tvg_id)
                    total_programmes += added
                    print(f"   {date_label}: {added} programmes")
                except Exception as e:
                    print(f"   {date_label}: ⚠️  FAILED — {e}")
                print()
        else:
            print("   ❌ Sepehr token is INVALID (may need rotation).\n")
    else:
        print("⏭️  Sepehr OAuth credentials not set — skipping TV channels.\n")

    # ── 2. Radio Quran (radioquran.ir, today only) ───────────────────────
    print("📻 Radio Quran (radioquran.ir):")

    # Register the Radio Quran channel definition
    rq_tvg_id = RADIO_QURAN["tvg_id"]
    ch_el = ET.SubElement(tv, "channel", id=rq_tvg_id)
    ET.SubElement(ch_el, "display-name").text = RADIO_QURAN["display_name"]
    ET.SubElement(ch_el, "icon", src=RADIO_QURAN["logo"])

    date_label = now.strftime("%Y-%m-%d")
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Primary: parse the HTML page (has descriptions + durations)
    rq_programmes = None
    print("   Trying HTML page (ChannelConductor)...")
    html = fetch_radio_quran_html()
    if html:
        rq_programmes = parse_radio_quran_html(html)
        if rq_programmes:
            has_descs = sum(1 for p in rq_programmes if p.get("description"))
            has_durs = sum(1 for p in rq_programmes if p.get("duration"))
            print(
                f"   ✅ HTML parsed: {len(rq_programmes)} programmes "
                f"({has_descs} with descriptions, {has_durs} with durations)"
            )
        else:
            print("   ⚠️  HTML fetched but no programmes parsed")

    # Fallback: JSON feed (no descriptions or durations, but lighter)
    if not rq_programmes:
        print("   Falling back to JSON feed...")
        rq_programmes = fetch_radio_quran_json()
        if rq_programmes:
            print(
                f"   ✅ JSON parsed: {len(rq_programmes)} programmes "
                f"(no descriptions/durations)"
            )

    if rq_programmes is None:
        print(f"   {date_label}: ⚠️  FAILED — both HTML and JSON returned nothing")
    elif not rq_programmes:
        print(f"   {date_label}: ⚠️  No programmes found in either source")
    else:
        added = radio_quran_to_xmltv(tv, rq_programmes, rq_tvg_id, day_start)
        if added > 0:
            radio_ok = True
            total_programmes += added
            print(f"   {date_label}: {added} programmes added to EPG")
        else:
            print(
                f"   {date_label}: ⚠️  No programmes converted "
                f"(page structure may have changed)"
            )
    print()

    # ── 3. Write output ──────────────────────────────────────────────────
    if total_programmes == 0:
        print("💀 No programmes from ANY source. EPG is completely empty!")
        sys.exit(1)

    xml_str = prettify_xml(tv)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"✅ Wrote {total_programmes} total programmes to {OUTPUT_FILE}")

    # ── 4. Report partial failures ───────────────────────────────────────
    if session and not sepehr_ok:
        print("\n⚠️  Sepehr failed but Radio Quran succeeded — partial EPG written.")
        print("   Sepehr OAuth keys may need rotation (see workflow issue).")

    if not radio_ok:
        print("\n⚠️  Radio Quran returned no data — only Sepehr TV in EPG.")

    if not sepehr_ok and not radio_ok:
        print("\n💀 All sources failed!")
        sys.exit(1)

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
