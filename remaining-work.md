Remaining gaps I found

### 🔴 Real reliability risks

1. **No workflow concurrency control** — if two scheduled runs overlap (or someone triggers manually while a cron run is in-flight), they'll race on the same `epg.xml` and potentially conflict on `git push`.

2. **Sepehr double-fetch** — `check_sepehr_token()` makes a full API call, and then the main loop immediately fetches the _same_ data again. Wasted round-trip and doubled rate-limit exposure.

3. **Last programme has no stop time** — if the final Radio Quran programme has no explicit duration and there's no next programme to infer from, it gets no `stop` attribute. Many EPG consumers (UHF, Jellyfin, TVHeadend) either hide that entry or show "Unknown end time."

4. **Action versions pinned to major tags, not SHAs** — `actions/checkout@v4`, `actions/github-script@v7`, etc. can be hijacked via tag mutation. Security best practice is to pin to full commit SHAs.

### 🟡 XMLTV compliance / quality

5. **No `date` attribute on `<tv>` root** — XMLTV standard includes `date="YYYYMMDD"` to tell consumers when the data was generated.

6. **No `<category>` elements** — adding a genre like "Religious" / "مذهبی" helps EPG UIs filter and display content properly.

7. **No `source-info-url` / `source-info-name`** — standard XMLTV traceability attributes.

### 🟢 Housekeeping

8. **README is outdated** — channels table says Radio Quran comes from "Sepehr API" (it's radioquran.ir now). Dependencies section doesn't mention `curl-cffi`.

9. **`.pytest_cache/` not in `.gitignore`** — it exists locally and could get accidentally committed.

10. **No `workflow_dispatch` inputs** — adding a "force" checkbox lets you bypass the drop-ratio guard when you _know_ a big drop is legitimate.
