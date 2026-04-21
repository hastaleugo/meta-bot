import aiohttp
import asyncio
import os
from datetime import datetime
from bs4 import BeautifulSoup

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
CHECK_INTERVAL = 3600

TIER_EMOJI = {
    "S": "🔴",
    "A": "🟠",
    "B": "🟡",
    "C": "⚪"
}

previous_meta = {}
message_id = None

def get_tier(winrate: float) -> str:
    if winrate >= 55:
        return "S"
    elif winrate >= 52:
        return "A"
    elif winrate >= 49:
        return "B"
    else:
        return "C"

async def fetch_meta() -> dict:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        # Klicker API de Brawltime Ninja
        url = "https://cube.brawltime.ninja/cubejs-api/v1/load"
        query = {
            "query": {
                "measures": ["brawler_battle.winRate", "brawler_battle.useRate"],
                "dimensions": ["brawler_battle.brawlerName"],
                "filters": [],
                "limit": 100,
                "order": {"brawler_battle.winRate": "desc"}
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=query,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                print(f"Cube status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    brawlers = {}
                    for row in data.get("data", []):
                        name = row.get("brawler_battle.brawlerName", "").strip().title()
                        winrate = round(float(row.get("brawler_battle.winRate", 0)) * 100, 1)
                        usage = round(float(row.get("brawler_battle.useRate", 0)) * 100, 2)
                        if name and winrate > 0:
                            brawlers[name] = {"winrate": winrate, "usage": usage}
                    return brawlers
    except Exception as e:
        print(f"Erreur cube: {e}")

    # Fallback : scraping page Brawltime
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://brawltime.ninja/tier-list/brawler",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                print(f"Scraping status: {resp.status}")
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    brawlers = {}
                    # Cherche les données JSON dans la page
                    scripts = soup.find_all("script")
                    for script in scripts:
                        if script.string and "winRate" in str(script.string):
                            print("Found winRate in script")
                    return brawlers
    except Exception as e:
        print(f"Erreur scraping: {e}")

    return {}

async def get_meta() -> list:
    data = await fetch_meta()
    if not data:
        return []

    sorted_brawlers = sorted(
        data.items(),
        key=lambda x: x[1]["winrate"],
        reverse=True
    )[:20]

    meta = []
    for name, stats in sorted_brawlers:
        tier = get_tier(stats["winrate"])
        meta.append({
            "name": name,
            "winrate": stats["winrate"],
            "usage": stats["usage"],
            "tier": tier
        })
    return meta

def build_embed(meta: list, changes: list) -> dict:
    now = datetime.now().strftime("%d/%m/%Y à %Hh%M")
    tier_groups = {"S": [], "A": [], "B": [], "C": []}
    for b in meta:
        tier_groups[b["tier"]].append(b)

    description = ""
    rank = 1
    for tier in ["S", "A", "B", "C"]:
        brawlers = tier_groups[tier]
        if not brawlers:
            continue
        description += f"\n{TIER_EMOJI[tier]} **Tier {tier}**\n"
        for b in brawlers:
            trend = ""
            for c in changes:
                if c["name"] == b["name"]:
                    trend = " `↑`" if c["direction"] == "up" else " `↓`"
            description += (
                f"`#{rank:02d}` **{b['name']}**{trend}\n"
                f"　　Win Rate: `{b['winrate']}%` • Usage: `{b['usage']}%`\n"
            )
            rank += 1

    return {
        "title": "🏆 META BRAWL STARS — TOP 20",
        "description": description,
        "color": 0x1E90FF,
        "footer": {"text": f"Mis à jour le {now} • Données en temps réel"},
        "thumbnail": {"url": "https://cdn.brawlify.com/brawlstars-logo.png"}
    }

def detect_changes(old_meta: dict, new_meta: list) -> list:
    changes = []
    tier_order = ["C", "B", "A", "S"]
    for b in new_meta:
        name = b["name"]
        if name in old_meta:
            old_tier = old_meta[name]["tier"]
            new_tier = b["tier"]
            if tier_order.index(new_tier) > tier_order.index(old_tier):
                changes.append({"name": name, "direction": "up", "old": old_tier, "new": new_tier})
            elif tier_order.index(new_tier) < tier_order.index(old_tier):
                changes.append({"name": name, "direction": "down", "old": old_tier, "new": new_tier})
    return changes

async def send_or_update_meta(meta: list, changes: list):
    global message_id
    embed = build_embed(meta, changes)

    async with aiohttp.ClientSession() as session:
        if message_id is None:
            payload = {
                "embeds": [embed],
                "username": "Brawl Stars Meta",
                "avatar_url": "https://cdn.brawlify.com/brawlstars-logo.png"
            }
            async with session.post(WEBHOOK_URL + "?wait=true", json=payload) as resp:
                if resp.status in [200, 204]:
                    data = await resp.json()
                    message_id = data.get("id")
                    print(f"✅ Message créé : {message_id}")
        else:
            webhook_id = WEBHOOK_URL.split("/")[-2]
            webhook_token = WEBHOOK_URL.split("/")[-1]
            edit_url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}"
            async with session.patch(edit_url, json={"embeds": [embed]}) as resp:
                if resp.status == 200:
                    print("✅ Message mis à jour")
                else:
                    print(f"⚠️ Erreur: {resp.status}")
                    message_id = None

async def send_alert(changes: list):
    if not changes:
        return
    lines = []
    for c in changes:
        arrow = "📈" if c["direction"] == "up" else "📉"
        lines.append(f"{arrow} **{c['name']}** : Tier {c['old']} → Tier {c['new']}")

    embed = {
        "title": "🚨 CHANGEMENT META DÉTECTÉ",
        "description": "\n".join(lines),
        "color": 0xFF4500,
        "footer": {"text": datetime.now().strftime("%d/%m/%Y à %Hh%M")}
    }
    async with aiohttp.ClientSession() as session:
        await session.post(WEBHOOK_URL, json={
            "content": "@everyone",
            "embeds": [embed],
            "username": "Brawl Stars Meta",
            "avatar_url": "https://cdn.brawlify.com/brawlstars-logo.png"
        })
    print(f"🚨 Alerte envoyée : {len(changes)} changements")

async def main():
    global previous_meta
    print("🚀 Bot Meta Brawl Stars lancé !")
    while True:
        print("🔄 Récupération de la meta...")
        meta = await get_meta()
        if meta:
            changes = detect_changes(previous_meta, meta)
            await send_or_update_meta(meta, changes)
            if changes:
                await send_alert(changes)
            previous_meta = {b["name"]: b for b in meta}
        else:
            print("⚠️ Impossible de récupérer la meta")
        print("⏳ Prochain check dans 1 heure...")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
