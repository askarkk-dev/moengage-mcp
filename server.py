#!/usr/bin/env python3
"""
MoEngage Analytics MCP Server
──────────────────────────────
Tools:
  1. search_campaigns     – find campaigns by channel / status / name
  2. get_campaign_stats   – stats for specific campaign IDs
  3. get_flow_stats       – journey / flow campaign breakdown
  4. compare_channels     – Push vs Email vs WhatsApp vs SMS vs In-App
  5. get_top_performers   – ranked campaigns by CTR / CVR / delivery
  6. whats_working        – scored cross-channel insight + recommendations

Deploy on Railway / Render / Fly.io, then add the HTTPS URL as a
Custom Connector in Claude.ai → Settings → Connectors.
"""

import asyncio
import base64
import os
from datetime import datetime, timedelta
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ── Server init ──────────────────────────────────────────────────────────────
mcp = FastMCP("moengage-analytics")

# ── Config (set as env vars on your host) ───────────────────────────────────
WORKSPACE_ID = os.environ.get("MOE_WORKSPACE_ID", "")
API_KEY      = os.environ.get("MOE_API_KEY", "")
DC           = os.environ.get("MOE_DC", "03")   # 01=US 02=EU 03=India 05=SG
BASE_URL     = f"https://api-{DC}.moengage.com"

CHANNELS = ["push", "email", "whatsapp", "sms", "inapp"]

CHANNEL_LABEL = {
    "push":     "Mobile Push",
    "email":    "Email",
    "whatsapp": "WhatsApp",
    "sms":      "SMS / RCS",
    "inapp":    "In-App",
}

# ── Auth & HTTP helpers ──────────────────────────────────────────────────────
def _headers() -> dict:
    token = base64.b64encode(f"{WORKSPACE_ID}:{API_KEY}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "MOE-APPKEY": WORKSPACE_ID,
        "Content-Type": "application/json",
    }


async def _post(path: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE_URL}{path}", json=payload, headers=_headers())
        r.raise_for_status()
        return r.json()


def _default_range() -> tuple[str, str]:
    end   = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    return start, end


def _chunks(lst: list, n: int = 10):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _pct(num: float, den: float) -> str:
    if not den:
        return "0.0%"
    return f"{num / den * 100:.1f}%"


def _extract_stats(raw: dict) -> dict:
    """Normalise the stats block regardless of MoEngage response shape."""
    s = raw.get("stats", raw.get("metrics", raw.get("data", {})))
    return {
        "sent":        s.get("sent", 0),
        "delivered":   s.get("delivered", 0),
        "impressions": s.get("impressions", s.get("opened", s.get("views", 0))),
        "clicks":      s.get("clicks", 0),
        "conversions": s.get("conversions", 0),
        "revenue":     s.get("revenue", 0.0),
    }


# ════════════════════════════════════════════════════════════════════════════
# TOOL 1 — Search campaigns
# ════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def search_campaigns(
    channel: str,
    status: str = "ACTIVE",
    name: str = "",
    limit: int = 20,
) -> str:
    """
    Search MoEngage campaigns by channel and status.

    Args:
        channel: push | email | whatsapp | sms | inapp
        status:  ACTIVE | COMPLETED | PAUSED | SCHEDULED | DRAFT  (default: ACTIVE)
        name:    Optional substring to filter by campaign name
        limit:   Max results to return (default 20, max 50)
    """
    payload: dict[str, Any] = {
        "status":  [status.upper()],
        "channel": channel.upper(),
        "size":    min(limit, 50),
    }
    if name:
        payload["name"] = name

    try:
        data = await _post("/campaigns/search", payload)
    except Exception as e:
        return f"❌ Error searching campaigns: {e}"

    campaigns = data.get("data", data.get("campaigns", []))
    if not campaigns:
        return f"No {channel} campaigns found (status={status})."

    lines = [f"Found {len(campaigns)} {CHANNEL_LABEL.get(channel.lower(), channel)} campaign(s) — status: {status}\n"]
    for c in campaigns:
        cid   = c.get("id", c.get("campaign_id", "N/A"))
        cname = c.get("name", "Unnamed")
        ctype = c.get("type", c.get("delivery_type", "N/A"))
        lines.append(f"• [{cid}]  {cname}  |  Type: {ctype}")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# TOOL 2 — Campaign stats for specific IDs
# ════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def get_campaign_stats(
    campaign_ids: str,
    start_date: str = "",
    end_date: str = "",
    metric_type: str = "UNIQUE",
) -> str:
    """
    Fetch performance stats for up to 10 campaign IDs.

    Args:
        campaign_ids: Comma-separated campaign IDs
        start_date:   YYYY-MM-DD  (default: 30 days ago)
        end_date:     YYYY-MM-DD  (default: today)
        metric_type:  UNIQUE | TOTAL  (default: UNIQUE)
    """
    if not start_date or not end_date:
        start_date, end_date = _default_range()

    ids = [x.strip() for x in campaign_ids.split(",") if x.strip()]
    if not ids:
        return "Provide at least one campaign ID."
    if len(ids) > 10:
        ids = ids[:10]
        note = "⚠️ Truncated to first 10 IDs.\n"
    else:
        note = ""

    try:
        data = await _post("/core-services/v1/campaign-stats", {
            "campaign_ids": ids,
            "start_date":   start_date,
            "end_date":     end_date,
            "metric_type":  metric_type.upper(),
        })
    except Exception as e:
        return f"❌ Error fetching stats: {e}"

    rows = data.get("data", [])
    if not rows:
        return "No stats returned for those IDs in that date range."

    lines = [f"{note}📊 Campaign Stats  {start_date} → {end_date}  [{metric_type}]\n"]
    for c in rows:
        name = c.get("campaign_name", c.get("name", str(c.get("campaign_id", "Unknown"))))
        s    = _extract_stats(c)

        lines += [
            f"\n▶ {name}",
            f"  Sent        : {s['sent']:,}",
            f"  Delivered   : {s['delivered']:,}  ({_pct(s['delivered'], s['sent'])})",
            f"  Impressions : {s['impressions']:,}  ({_pct(s['impressions'], s['delivered'] or s['sent'])})",
            f"  Clicks      : {s['clicks']:,}  CTR {_pct(s['clicks'], s['impressions'] or s['sent'])}",
            f"  Conversions : {s['conversions']:,}  CVR {_pct(s['conversions'], s['clicks'] or s['impressions'])}",
            f"  Revenue     : ₹{s['revenue']:,.0f}" if s["revenue"] else "",
        ]

    return "\n".join(l for l in lines if l != "")


# ════════════════════════════════════════════════════════════════════════════
# TOOL 3 — Flow / Journey stats
# ════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def get_flow_stats(
    campaign_ids: str,
    start_date: str = "",
    end_date: str = "",
) -> str:
    """
    Get stats for all campaign steps inside a MoEngage Flow / Journey.
    Pass the individual campaign IDs from the flow canvas (comma-separated).

    Args:
        campaign_ids: Comma-separated campaign IDs from the flow
        start_date:   YYYY-MM-DD  (default: 30 days ago)
        end_date:     YYYY-MM-DD  (default: today)
    """
    if not start_date or not end_date:
        start_date, end_date = _default_range()

    ids = [x.strip() for x in campaign_ids.split(",") if x.strip()]
    if not ids:
        return "Provide at least one campaign ID from the flow."

    all_rows: list[dict] = []
    for batch in _chunks(ids, 10):
        try:
            data = await _post("/core-services/v1/campaign-stats", {
                "campaign_ids": batch,
                "start_date":   start_date,
                "end_date":     end_date,
                "metric_type":  "UNIQUE",
            })
            all_rows.extend(data.get("data", []))
        except Exception as e:
            return f"❌ Error: {e}"

    if not all_rows:
        return "No stats returned."

    totals = {"sent": 0, "delivered": 0, "impressions": 0, "clicks": 0, "conversions": 0, "revenue": 0.0}
    lines  = [f"🔄 Flow Stats  {start_date} → {end_date}\n"]

    for c in all_rows:
        name = c.get("campaign_name", c.get("name", str(c.get("campaign_id", "Step"))))
        s    = _extract_stats(c)
        for k in totals:
            totals[k] += s[k]

        lines += [
            f"\n📌 {name}",
            f"  Sent: {s['sent']:,}  |  Delivered: {s['delivered']:,} ({_pct(s['delivered'], s['sent'])})",
            f"  Impressions: {s['impressions']:,}  |  Clicks: {s['clicks']:,} (CTR {_pct(s['clicks'], s['impressions'] or s['sent'])})",
            f"  Conversions: {s['conversions']:,} (CVR {_pct(s['conversions'], s['clicks'] or s['impressions'])})",
        ]

    lines += [
        "\n── Flow Totals ─────────────────────────────",
        f"  Total Sent        : {totals['sent']:,}",
        f"  Total Clicks      : {totals['clicks']:,}  (CTR {_pct(totals['clicks'], totals['impressions'] or totals['sent'])})",
        f"  Total Conversions : {totals['conversions']:,}  (CVR {_pct(totals['conversions'], totals['clicks'])})",
        f"  Total Revenue     : ₹{totals['revenue']:,.0f}" if totals["revenue"] else "",
    ]

    return "\n".join(l for l in lines if l != "")


# ════════════════════════════════════════════════════════════════════════════
# TOOL 4 — Channel-wise comparison
# ════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def compare_channels(
    start_date: str = "",
    end_date: str = "",
    status: str = "COMPLETED",
) -> str:
    """
    Compare Push, Email, WhatsApp, SMS/RCS, and In-App side by side.

    Args:
        start_date: YYYY-MM-DD  (default: 30 days ago)
        end_date:   YYYY-MM-DD  (default: today)
        status:     Campaign status to include (default: COMPLETED)
    """
    if not start_date or not end_date:
        start_date, end_date = _default_range()

    summary: dict[str, dict] = {}

    for ch in CHANNELS:
        try:
            sd = await _post("/campaigns/search", {
                "status":  [status.upper()],
                "channel": ch.upper(),
                "size":    50,
            })
            campaigns = sd.get("data", sd.get("campaigns", []))
        except Exception:
            summary[ch] = {"error": True}
            continue

        ids = [str(c.get("id", c.get("campaign_id", ""))) for c in campaigns
               if c.get("id") or c.get("campaign_id")]

        if not ids:
            summary[ch] = {"campaigns": 0, "sent": 0, "delivered": 0,
                           "impressions": 0, "clicks": 0, "conversions": 0}
            continue

        agg: dict[str, Any] = {
            "campaigns": len(ids), "sent": 0, "delivered": 0,
            "impressions": 0, "clicks": 0, "conversions": 0,
        }

        for batch in _chunks(ids, 10):
            try:
                sd2 = await _post("/core-services/v1/campaign-stats", {
                    "campaign_ids": batch,
                    "start_date":   start_date,
                    "end_date":     end_date,
                    "metric_type":  "UNIQUE",
                })
                for c in sd2.get("data", []):
                    s = _extract_stats(c)
                    for k in ("sent", "delivered", "impressions", "clicks", "conversions"):
                        agg[k] += s[k]
            except Exception:
                pass

        summary[ch] = agg

    # ── Format table ────────────────────────────────────────────────────────
    lines = [f"📊 Channel Comparison  {start_date} → {end_date}  (status: {status})\n"]
    lines.append(f"{'Channel':<18} {'Camps':>6} {'Sent':>10} {'Del%':>7} {'CTR':>7} {'CVR':>7}")
    lines.append("─" * 60)

    scored = []
    for ch in CHANNELS:
        d = summary.get(ch, {})
        if d.get("error"):
            lines.append(f"{CHANNEL_LABEL[ch]:<18} {'ERROR':>6}")
            continue

        camps = d.get("campaigns", 0)
        sent  = d.get("sent", 0)
        imps  = d.get("impressions", 0)
        clicks = d.get("clicks", 0)
        convs  = d.get("conversions", 0)
        deliv  = d.get("delivered", 0)

        dr  = deliv  / max(sent, 1)
        ctr = clicks / max(imps or sent, 1)
        cvr = convs  / max(clicks or imps, 1)

        lines.append(
            f"{CHANNEL_LABEL[ch]:<18} {camps:>6} {sent:>10,} "
            f"{_pct(deliv, sent):>7} {_pct(clicks, imps or sent):>7} "
            f"{_pct(convs, clicks or imps):>7}"
        )

        if sent > 0:
            scored.append((ch, ctr, cvr, dr))

    if scored:
        best_ctr  = max(scored, key=lambda x: x[1])
        best_cvr  = max(scored, key=lambda x: x[2])
        best_del  = max(scored, key=lambda x: x[3])
        lines += [
            "",
            f"🏆 Best CTR      → {CHANNEL_LABEL[best_ctr[0]]}  ({_pct(best_ctr[1]*100, 100)})",
            f"🏆 Best CVR      → {CHANNEL_LABEL[best_cvr[0]]}  ({_pct(best_cvr[1]*100, 100)})",
            f"🏆 Best Delivery → {CHANNEL_LABEL[best_del[0]]}  ({_pct(best_del[2]*100, 100)})",
        ]

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# TOOL 5 — Top performers
# ════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def get_top_performers(
    channel: str = "all",
    metric: str = "ctr",
    start_date: str = "",
    end_date: str = "",
    top_n: int = 5,
) -> str:
    """
    Find the top-performing campaigns by a given metric.

    Args:
        channel:    push | email | whatsapp | sms | inapp | all  (default: all)
        metric:     ctr | cvr | delivery_rate | sent  (default: ctr)
        start_date: YYYY-MM-DD  (default: 30 days ago)
        end_date:   YYYY-MM-DD  (default: today)
        top_n:      How many to return (default 5)
    """
    if not start_date or not end_date:
        start_date, end_date = _default_range()

    channels_to_check = CHANNELS if channel.lower() == "all" else [channel.lower()]
    pool: list[dict] = []

    for ch in channels_to_check:
        try:
            sd = await _post("/campaigns/search", {
                "status":  ["COMPLETED"],
                "channel": ch.upper(),
                "size":    50,
            })
            campaigns = sd.get("data", sd.get("campaigns", []))
        except Exception:
            continue

        id_to_name = {
            str(c.get("id", c.get("campaign_id", ""))): c.get("name", "Unknown")
            for c in campaigns
        }
        ids = list(id_to_name.keys())

        for batch in _chunks(ids, 10):
            try:
                sd2 = await _post("/core-services/v1/campaign-stats", {
                    "campaign_ids": batch,
                    "start_date":   start_date,
                    "end_date":     end_date,
                    "metric_type":  "UNIQUE",
                })
                for c in sd2.get("data", []):
                    cid = str(c.get("campaign_id", c.get("id", "")))
                    s   = _extract_stats(c)
                    if s["sent"] == 0:
                        continue
                    pool.append({
                        "name":          id_to_name.get(cid, cid),
                        "channel":       CHANNEL_LABEL.get(ch, ch),
                        "sent":          s["sent"],
                        "delivered":     s["delivered"],
                        "impressions":   s["impressions"],
                        "clicks":        s["clicks"],
                        "conversions":   s["conversions"],
                        "ctr":           s["clicks"] / max(s["impressions"] or s["sent"], 1),
                        "cvr":           s["conversions"] / max(s["clicks"] or s["impressions"], 1),
                        "delivery_rate": s["delivered"] / max(s["sent"], 1),
                    })
            except Exception:
                pass

    if not pool:
        return "No campaign data found."

    sort_key = metric.lower() if metric.lower() in ("ctr", "cvr", "delivery_rate", "sent") else "ctr"
    top = sorted(pool, key=lambda x: x[sort_key], reverse=True)[:top_n]

    lines = [f"🏆 Top {top_n} by {sort_key.upper()}  {start_date} → {end_date}\n"]
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, top_n + 1)]

    for medal, c in zip(medals, top):
        lines += [
            f"{medal} {c['name']}  [{c['channel']}]",
            f"   Sent: {c['sent']:,}  |  Del%: {_pct(c['delivery_rate']*100,100)}  "
            f"|  CTR: {_pct(c['ctr']*100,100)}  |  CVR: {_pct(c['cvr']*100,100)}",
        ]

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# TOOL 6 — What's working (scored insight)
# ════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def whats_working(
    start_date: str = "",
    end_date: str = "",
) -> str:
    """
    Score all channels and surface what's performing best with actionable recommendations.
    Scoring: CTR 40% + CVR 40% + Delivery Rate 20%.

    Args:
        start_date: YYYY-MM-DD  (default: 30 days ago)
        end_date:   YYYY-MM-DD  (default: today)
    """
    if not start_date or not end_date:
        start_date, end_date = _default_range()

    scored: list[tuple] = []

    for ch in CHANNELS:
        try:
            sd = await _post("/campaigns/search", {
                "status":  ["COMPLETED"],
                "channel": ch.upper(),
                "size":    50,
            })
            campaigns = sd.get("data", sd.get("campaigns", []))
        except Exception:
            continue

        ids = [str(c.get("id", c.get("campaign_id", ""))) for c in campaigns
               if c.get("id") or c.get("campaign_id")]
        if not ids:
            continue

        agg: dict[str, float] = {
            "campaigns": len(ids), "sent": 0, "delivered": 0,
            "impressions": 0, "clicks": 0, "conversions": 0,
        }

        for batch in _chunks(ids, 10):
            try:
                sd2 = await _post("/core-services/v1/campaign-stats", {
                    "campaign_ids": batch,
                    "start_date":   start_date,
                    "end_date":     end_date,
                    "metric_type":  "UNIQUE",
                })
                for c in sd2.get("data", []):
                    s = _extract_stats(c)
                    for k in ("sent", "delivered", "impressions", "clicks", "conversions"):
                        agg[k] += s[k]
            except Exception:
                pass

        if agg["sent"] == 0:
            continue

        ctr = agg["clicks"]      / max(agg["impressions"] or agg["sent"], 1)
        cvr = agg["conversions"] / max(agg["clicks"] or agg["impressions"], 1)
        dr  = agg["delivered"]   / max(agg["sent"], 1)
        score = ctr * 0.4 + cvr * 0.4 + dr * 0.2

        scored.append((ch, agg, ctr, cvr, dr, score))

    if not scored:
        return "No data available for the given date range."

    scored.sort(key=lambda x: x[5], reverse=True)
    medals = ["🥇", "🥈", "🥉"] + ["  " for _ in range(10)]

    lines = [f"🔍 What's Working  {start_date} → {end_date}\n"]

    for medal, (ch, agg, ctr, cvr, dr, score) in zip(medals, scored):
        lines += [
            f"{medal} {CHANNEL_LABEL[ch]}  (score: {score:.4f})",
            f"   Campaigns: {int(agg['campaigns'])}  |  Sent: {int(agg['sent']):,}",
            f"   Delivery: {_pct(dr*100,100)}  |  CTR: {_pct(ctr*100,100)}  |  CVR: {_pct(cvr*100,100)}",
            "",
        ]

    # Recommendations
    recs = []
    for ch, agg, ctr, cvr, dr, _ in scored:
        label = CHANNEL_LABEL[ch]
        if ctr < 0.02:
            recs.append(f"• {label}: Low CTR — revisit copy, subject lines, or send-time")
        if dr < 0.70 and agg["sent"] > 500:
            recs.append(f"• {label}: Low delivery — check opt-in health, DND/FC settings")
        if cvr < 0.01 and agg["clicks"] > 100:
            recs.append(f"• {label}: Low CVR — review landing page or offer relevance")

    if recs:
        lines.append("💡 Recommendations:")
        lines.extend(recs)

    winner = scored[0]
    lines.append(f"\n✅ Lead channel: {CHANNEL_LABEL[winner[0]]} "
                 f"(CTR {_pct(winner[2]*100,100)}, CVR {_pct(winner[3]*100,100)})")

    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
