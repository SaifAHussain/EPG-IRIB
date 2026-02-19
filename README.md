# EPG-IRIB 🕌

Automated XMLTV EPG (Electronic Programme Guide) for **IRIB Quran** and **Radio Quran** — designed to run on GitHub Actions and serve via GitHub Pages so you never have to touch it again.

## What This Does

A single Python script (`generate_epg.py`) that:

1. Fetches **IRIB Quran** and **Radio Quran** schedules from IRIB's official Sepehr API
2. Signs every API request with OAuth 1.0 (HMAC-SHA1) using per-request signatures
3. Outputs `epg.xml` in standard XMLTV format
4. GitHub Actions runs this every 6 hours and commits the updated XML
5. GitHub Pages serves `epg.xml` at a public URL you paste into UHF (or any IPTV app)

## Channels

| Channel     | Source     | tvg-id (for M3U) |
| ----------- | ---------- | ---------------- |
| IRIB Quran  | Sepehr API | `QuranTV.ir@SD`  |
| Radio Quran | Sepehr API | `Radio Quran`    |

## Setup

### 1. Configure GitHub Secrets

The generator needs four OAuth 1.0 credentials stored as **GitHub Actions Secrets**:

| Secret Name              | Description                 |
| ------------------------ | --------------------------- |
| `SEPEHR_CONSUMER_KEY`    | OAuth consumer key          |
| `SEPEHR_CONSUMER_SECRET` | OAuth consumer secret       |
| `SEPEHR_ACCESS_TOKEN`    | OAuth access/resource token |
| `SEPEHR_TOKEN_SECRET`    | OAuth token secret          |

Go to **repo Settings → Secrets and variables → Actions** and add all four.

To find these values, see [Credential Rotation](#credential-rotation) below.

### 2. Enable GitHub Pages

1. Go to your repo on GitHub → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / `/ (root)`
4. Save — your EPG will be at:
   ```
   https://YOUR_USERNAME.github.io/EPG-IRIB/epg.xml
   ```

### 3. Update your M3U

Make sure the `tvg-id` values match:

```m3u
#EXTM3U

#EXTINF:-1 tvg-id="QuranTV.ir@SD" tvg-logo="https://lb-cdn.sepehrtv.ir/img/channel/quarnlogo.png" group-title="Religious",IRIB Quran
https://live-azd1104.telewebion.ir/ek/quran/live/1080p/index.m3u8

#EXTINF:-1 tvg-id="Radio Quran" tvg-logo="https://logoyab.com/wp-content/uploads/2024/08/Radio-Quran-Logo.png" group-title="Quran",Radio Quran
https://live-azd1103.telewebion.ir/ek/radioquran/live/576p/index.m3u8
```

### 4. Add EPG URL to UHF

1. Open **UHF** on Apple TV
2. Edit your playlist → find **EPG URL** / **Guide** field
3. Paste: `https://YOUR_USERNAME.github.io/EPG-IRIB/epg.xml`
4. Save and let it refresh

## Running Locally

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set credentials (create a .env file — it's in .gitignore)
cat > .env << 'EOF'
SEPEHR_CONSUMER_KEY=your_consumer_key_here
SEPEHR_CONSUMER_SECRET=your_consumer_secret_here
SEPEHR_ACCESS_TOKEN=your_access_token_here
SEPEHR_TOKEN_SECRET=your_token_secret_here
EOF

# Generate EPG
uv run generate_epg.py
```

This produces `epg.xml` in the current directory. The script reads credentials from `.env` automatically (via `python-dotenv`).

## Maintenance

**Normally: none.** GitHub Actions refreshes the EPG every 6 hours automatically.

If credentials expire, the workflow will fail and auto-create a GitHub Issue labelled `epg-failed`.

### Credential Rotation

When Sepehr rotates their app-level OAuth keys:

1. Go to [sepehrtv.ir](https://sepehrtv.ir)
2. Open DevTools → **Sources** tab
3. Search the JavaScript bundles for `consumer` or `getAuthHeaderForRequest`
4. Extract the four values:
   - Consumer Key
   - Consumer Secret
   - Access Token (resource owner key)
   - Token Secret (resource owner secret)
5. Update GitHub Secrets:
   ```bash
   gh secret set SEPEHR_CONSUMER_KEY    --body 'new_consumer_key'
   gh secret set SEPEHR_CONSUMER_SECRET --body 'new_consumer_secret'
   gh secret set SEPEHR_ACCESS_TOKEN    --body 'new_access_token'
   gh secret set SEPEHR_TOKEN_SECRET    --body 'new_token_secret'
   ```
   Or update them manually at **repo Settings → Secrets and variables → Actions**.
6. Re-run the workflow: **Actions → Update EPG → Run workflow**
7. If an `epg-failed` issue was created, close it once the run succeeds.

> **⚠️ Never commit credentials to the repo.** Use GitHub Secrets for CI and `.env` for local runs. The `.env` file is in `.gitignore`.

## Troubleshooting

| Symptom                              | Likely Cause                       | Fix                                                             |
| ------------------------------------ | ---------------------------------- | --------------------------------------------------------------- |
| `⚠️ OAuth credentials not fully set` | Missing env vars / secrets         | Set all four `SEPEHR_*` env vars                                |
| `❌ OAuth credentials failed`        | Sepehr rotated their keys          | Follow [Credential Rotation](#credential-rotation)              |
| `0 programmes fetched`               | API returned empty data            | Check if Sepehr is down; try a different `channel_id` manually  |
| Workflow fails silently              | GitHub Actions quota / permissions | Check Actions tab for logs; ensure `contents: write` permission |

## Dependencies

- Python ≥ 3.11
- `requests-oauthlib` — OAuth 1.0 request signing
- `python-dotenv` — loads `.env` for local development

Managed via `uv` — see `pyproject.toml`.

## License

MIT
