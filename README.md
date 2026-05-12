# MoEngage Analytics MCP Server

Exposes 6 tools for campaign stats, flow stats, channel comparison, and performance insights — for use as a Claude.ai custom connector.

---

## Tools

| Tool | What it does |
|---|---|
| `search_campaigns` | Find campaigns by channel / status / name |
| `get_campaign_stats` | Stats for specific campaign IDs |
| `get_flow_stats` | Per-step breakdown for a Flow / Journey |
| `compare_channels` | Push vs Email vs WhatsApp vs SMS vs In-App table |
| `get_top_performers` | Ranked campaigns by CTR / CVR / delivery / sent |
| `whats_working` | Scored cross-channel analysis + recommendations |

---

## Environment Variables

Set these on your hosting platform:

| Variable | Description |
|---|---|
| `MOE_WORKSPACE_ID` | Your MoEngage Workspace ID (from Settings → Account → APIs) |
| `MOE_API_KEY` | Campaign Report API Key (same location) |
| `MOE_DC` | Data center number — `01` US, `02` EU, `03` India, `05` SG |

---

## Local setup

```bash
pip install -r requirements.txt
export MOE_WORKSPACE_ID=your_workspace_id
export MOE_API_KEY=your_api_key
export MOE_DC=03
python server.py
```

---

## Deploy to Railway (recommended)

1. Push this folder to a GitHub repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Set the 3 environment variables in Railway's Variables tab
4. Railway will auto-detect Python and run `python server.py`
5. Copy the public HTTPS URL Railway gives you (e.g. `https://moengage-mcp.railway.app`)

## Deploy to Render

1. Push to GitHub
2. New Web Service → connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `python server.py`
5. Add env vars in Render's Environment tab
6. Copy the `.onrender.com` HTTPS URL

---

## Connect to Claude.ai

1. Open [claude.ai](https://claude.ai) → Settings → Connectors
2. Click **Add Connector** → **Custom Connector**
3. Paste your HTTPS URL (e.g. `https://moengage-mcp.railway.app`)
4. Click Connect
5. You'll see 6 MoEngage tools listed under Connectors

---

## Example prompts (once connected)

```
Search all completed WhatsApp campaigns from the last 30 days

Get campaign stats for IDs abc123, def456 from 2025-04-01 to 2025-04-30

Compare all channels for April and tell me what's working

Show me the top 5 campaigns by CTR across all channels this month

Get flow stats for campaign IDs from my uninstall winback journey
```

---

## Notes

- Max 10 campaign IDs per `get_campaign_stats` call (MoEngage API limit)
- `compare_channels` and `whats_working` auto-batch across all channels
- Flow stats require the individual campaign IDs from the flow canvas (not the flow ID)
- All stats use `UNIQUE` metric type by default
- Revenue metric shown only if tracked in MoEngage
