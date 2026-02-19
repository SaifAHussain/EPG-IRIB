# EPG-IRIB 🕌

Automated XMLTV EPG (Electronic Programme Guide) for **IRIB Quran** and **Radio Quran** — designed to run on GitHub Actions and serve via GitHub Pages so you never have to touch it again.

## What This Does

A single Python script (`generate_epg.py`) that:

1. Fetches **IRIB Quran** and **Radio Quran** schedules from IRIB's official Sepehr API (7 days of data)
2. Outputs `epg.xml` in standard XMLTV format
3. GitHub Actions runs this every 6 hours and commits the updated XML
4. GitHub Pages serves `epg.xml` at a public URL you paste into UHF (or any IPTV app)

## Channels

| Channel     | Source     | tvg-id (for M3U) |
| ----------- | ---------- | ---------------- |
| IRIB Quran  | Sepehr API | `QuranTV.ir@SD`  |
| Radio Quran | Sepehr API | `Radio Quran`    |

## Setup

### 1. Enable GitHub Pages

1. Go to your repo on GitHub → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / `/ (root)`
4. Save — your EPG will be at:
   ```
   https://YOUR_USERNAME.github.io/EPG-IRIB/epg.xml
   ```

### 2. Update your M3U

Make sure the `tvg-id` values match:

```m3u
#EXTM3U

#EXTINF:-1 tvg-id="QuranTV.ir@SD" tvg-logo="https://lb-cdn.sepehrtv.ir/img/channel/quarnlogo.png" group-title="Religious",IRIB Quran
https://live-azd1104.telewebion.ir/ek/quran/live/1080p/index.m3u8

#EXTINF:-1 tvg-id="Radio Quran" tvg-logo="https://logoyab.com/wp-content/uploads/2024/08/Radio-Quran-Logo.png" group-title="Quran",Radio Quran
https://live-azd1103.telewebion.ir/ek/radioquran/live/576p/index.m3u8
```

### 3. Add EPG URL to UHF

1. Open **UHF** on Apple TV
2. Edit your playlist → find **EPG URL** / **Guide** field
3. Paste: `https://YOUR_USERNAME.github.io/EPG-IRIB/epg.xml`
4. Save and let it refresh

## Running Locally

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Generate EPG
export OAUTH_HEADER='OAuth oauth_consumer_key="...", ...'
uv run generate_epg.py
```

This produces `epg.xml` in the current directory.

## Maintenance

**Normally: none.** GitHub Actions refreshes the EPG every 6 hours automatically.

**When the IRIB token expires:** GitHub will auto-create an issue. To fix:

1. Go to [sepehrtv.ir](https://sepehrtv.ir)
2. Open DevTools → Network tab
3. Find any request to `sepehrapi.sepehrtv.ir`
4. Copy the full `Authorization` header value (starts with `OAuth oauth_consumer_key=...`)
5. Update the GitHub Secret:
   ```bash
   gh secret set OAUTH_HEADER --body 'OAuth oauth_consumer_key="...", ...'
   ```
   Or go to **repo Settings → Secrets and variables → Actions → OAUTH_HEADER** and paste the new value.
6. Re-run the workflow (Actions → Update EPG → Run workflow)

> **⚠️ The token is stored as a GitHub Secret, never in the code.**

## Dependencies

- Python ≥ 3.11
- `requests`

Managed via `uv` — see `pyproject.toml`.

## License

MIT
