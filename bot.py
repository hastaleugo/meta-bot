import aiohttp
import asyncio
import os
from datetime import datetime

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
CHECK_INTERVAL = 3600

BRAWLIFY_URL = "https://api.brawlify.com/v1/brawlers"

TIERS = {
    (55, 100): "S",
    (52, 55): "A",
    (49, 52): "B",
    (0, 49): "C"
}

TIER_EMOJI = {
    "S": "🔴",
    "A": "🟠",
    "B": "🟡",
    "C": "⚪"
}

previous_meta = {}
message_id = None

def get_tier(winrate: float) -> str:
    for (low, high), tier in TIERS.items():
        if low <= winrate < high:
            return tier
    return "C"

async def fetch_brawltime() -> dict:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://brawltime.ninja/",
            "Origin": "https://brawltime.ninja"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                BRAWLTIME_URL,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                print(f"Brawltime status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    brawlers = {}
                    for item in data.get("brawlers", []):
                        name = item.get("name", "").strip()
                        winrate = round(float(item.get("stats", {}).get("winRate", 0)) * 100, 1)
                        usage = round(float(item.get("stats", {}).get("useRate", 0)) * 100, 2)
                        if name and winrate > 0:
                            brawlers[name] = {
                                "winrate": winrate,
                                "usage": usage
                            }
                    return brawlers
                else:
                    print(f"Brawltime erreur: {resp.status}")
    except Exception as e:
        print(f"Erreur Brawltime: {e}")
    return {}

async def get_meta() -> list:
    brawltime_data = await fetch_brawltime()
    if not brawltime_data:
        return []

    sorted_brawlers = sorted(
        brawltime_data.items(),
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

    embed = {
        "title": "🏆 META BRAWL STARS — TOP 20",
        "description": description,
        "color": 0x1E90FF,
        "footer": {
            "text": f"Mis à jour le {now} • Données en temps réel"
        },
        "thumbnail": {
            "url": "https://cdn.brawlify.com/brawlstars-logo.png"
        }
    }

    return embed

def detect_changes(old_meta: dict, new_meta: list) -> list:
    changes = []
    tier_order = ["C", "B", "A", "S"]
    for b in new_meta:
        name = b["name"]
        new_tier = b["tier"]
        if name in old_meta:
            old_tier = old_meta[name]["tier"]
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
            async with session.post(
                WEBHOOK_URL + "?wait=true",
                json=payload
            ) as resp:
                if resp.status in [200, 204]:
                    data = await resp.json()
                    message_id = data.get("id")
                    print(f"✅ Message meta créé : {message_id}")
                else:
                    print(f"⚠️ Erreur envoi: {resp.status}")
        else:
            webhook_id = WEBHOOK_URL.split("/")[-2]
            webhook_token = WEBHOOK_URL.split("/")[-1]
            edit_url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}"

            payload = {"embeds": [embed]}
            async with session.patch(edit_url, json=payload) as resp:
                if resp.status == 200:
                    print("✅ Message meta mis à jour")
                else:
                    print(f"⚠️ Erreur mise à jour: {resp.status} — recréation")
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
        "footer": {
            "text": datetime.now().strftime("%d/%m/%Y à %Hh%M")
        }
    }

    async with aiohttp.ClientSession() as session:
        payload = {
            "content": "@everyone",
            "embeds": [embed],
            "username": "Brawl Stars Meta",
            "avatar_url": "https://cdn.brawlify.com/brawlstars-logo.png"
        }
        await session.post(WEBHOOK_URL, json=payload)
        print(f"🚨 Alerte meta envoyée : {len(changes)} changements")

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
