"""
Telescope Daily & Weekly Brief
- Daglig brief kl. 07:30 (man-fre)
- Ukentlig brief kl. 07:30 (mandag)

Kjør: python telescope_brief.py
"""

import schedule
import time
import requests
from datetime import datetime, timedelta
from anthropic import Anthropic

# ── CONFIG ────────────────────────────────────────────────────────────────────

SLACK_BOT_TOKEN   = "xoxb-your-slack-bot-token"   # Hent fra Slack App-innstillinger
HUBSPOT_API_KEY   = "eu1-c2d4-91eb-47e1-bea1-374d66f6f8f0"       # Regenerer på HubSpot etter å ha slettet den forrige
NOTION_API_KEY    = "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"        # Regenerer på notion.so/my-integrations
ANTHROPIC_API_KEY = "your-anthropic-api-key"       # Hent fra console.anthropic.com
GUSTAV_USER_ID    = "U044K2ZEPGQ"

SLACK_CHANNELS_TO_WATCH = [
    "C09BHRU20PR",  # #sales
    "C05DK33MGUU",  # #pr-review
    "C08MSPNEYM7",  # #customer-success
]

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ── DATAFETCHING ──────────────────────────────────────────────────────────────

def fetch_slack_activity(hours_back=24):
    since = int((datetime.now() - timedelta(hours=hours_back)).timestamp())
    messages = []
    for channel_id in SLACK_CHANNELS_TO_WATCH:
        r = requests.get(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"channel": channel_id, "oldest": since, "limit": 20}
        )
        data = r.json()
        if data.get("ok"):
            for msg in data.get("messages", []):
                if msg.get("text") and not msg.get("bot_id"):
                    messages.append({
                        "channel": channel_id,
                        "user": msg.get("user", "unknown"),
                        "text": msg["text"][:300],
                        "ts": msg["ts"]
                    })
    return messages


def fetch_hubspot_deals(days_back=1):
    since_ms = int((datetime.now() - timedelta(days=days_back)).timestamp() * 1000)
    r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/deals/search",
        headers={
            "Authorization": f"Bearer {HUBSPOT_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "filterGroups": [{
                "filters": [{
                    "propertyName": "hs_lastmodifieddate",
                    "operator": "GTE",
                    "value": str(since_ms)
                }]
            }],
            "properties": ["dealname", "dealstage", "amount", "hubspot_owner_id"],
            "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "DESCENDING"}],
            "limit": 20
        }
    )
    return r.json().get("results", [])


def fetch_pr_review_activity(hours_back=24):
    since = int((datetime.now() - timedelta(hours=hours_back)).timestamp())
    r = requests.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        params={"channel": "C05DK33MGUU", "oldest": since, "limit": 50}
    )
    data = r.json()
    if not data.get("ok"):
        return []
    msgs = data.get("messages", [])
    deploys, unreviewed, contributors = [], [], set()
    for m in msgs:
        text = m.get("text", "")
        if "Deploying" in text and "to `prod`" in text:
            deploys.append(text[:200])
            for line in text.split("\n"):
                if "Triggered by:" in text:
                    idx = text.find("Triggered by:") + 14
                    name = text[idx:idx+30].strip().split("\n")[0]
                    contributors.add(name)
        if "Unreviewed PRs" in text:
            unreviewed.append(text[:500])
    return {
        "deploys": deploys,
        "unreviewed_summary": unreviewed[0] if unreviewed else "",
        "contributors": list(contributors)
    }


def fetch_notion_updates():
    r = requests.post(
        "https://api.notion.com/v1/search",
        headers={
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        },
        json={
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": 10
        }
    )
    pages = r.json().get("results", [])
    return [
        {
            "title": p.get("properties", {}).get("title", {}).get("title", [{}])[0].get("text", {}).get("content", "Untitled") if p.get("properties", {}).get("title") else "Untitled",
            "edited": p.get("last_edited_time", "")
        }
        for p in pages
    ]


# ── BRIEF GENERATION ──────────────────────────────────────────────────────────

def generate_brief(brief_type="daily"):
    days_back = 1 if brief_type == "daily" else 7
    hours_back = 24 if brief_type == "daily" else 168

    slack   = fetch_slack_activity(hours_back=hours_back)
    deals   = fetch_hubspot_deals(days_back=days_back)
    tech    = fetch_pr_review_activity(hours_back=hours_back)
    notion  = fetch_notion_updates()
    today   = datetime.now().strftime("%-d. %B %Y")

    if brief_type == "daily":
        prompt = f"""
Du er en AI-assistent for Gustav Haaland, CEO i Telescope – et klimarisiko-selskap for eiendomssektoren.
Lag en kort daglig brief basert på dataene under. Skriv på norsk. Bruk Slack markdown (*bold*, bullet points).

FORMAT (følg nøyaktig):
☀️ *God morgen, Gustav — {today}*

*🔥 Haster i dag*
(maks 3 punkter, det mest kritiske)

---

*💸 Sales (siste 24t)*
(deals oppdatert i HubSpot, hvem eier hva, status)

---

*💬 Slack-høydepunkter*
(viktigste meldinger fra kanalene)

---

*⚙️ Tech (siste 24t)*
Deployer til prod: X stk
• (liste over commits/deployer med hvem som trigget)

Top contributors:
• (navn — hva de jobbet med)

Trenger oppmerksomhet:
• (PRs som hoper seg opp, blokkerte ting)

DATA:
SLACK: {slack}
HUBSPOT DEALS: {deals}
TECH/PR: {tech}
NOTION: {notion}
"""
    else:
        week_num = datetime.now().isocalendar()[1]
        prompt = f"""
Du er en AI-assistent for Gustav Haaland, CEO i Telescope.
Lag en ukentlig oppsummering basert på dataene. Skriv på norsk. Bruk Slack markdown.

FORMAT (følg nøyaktig):
📅 *Ukesoppsummering — uke {week_num}*

---

*🏆 Ukens høydepunkter*
(3-5 viktigste ting som skjedde)

---

*💸 Sales — ukesoppsummering*

*Fremgang:*
(deals som beveget seg fremover)

*Stiller:*
(deals uten aktivitet eller blokkerte)

*Tapt denne uken:*
(closed lost)

*Pipeline-eiere:*
(hvem eier hva, kort oppsummert)

---

*⚙️ Tech — ukesoppsummering*

Deployer til prod: X stk
(viktigste commits)

Top contributors:
• (navn — hva de bidro med)

Teknisk gjeld:
• (PRs som hoper seg opp)

---

*💬 Viktigste Slack-tema denne uken*
(3-4 temaer som gikk igjen)

---

*🎯 Fokus neste uke*
(3-5 konkrete prioriteringer basert på dataene)

DATA:
SLACK: {slack}
HUBSPOT DEALS: {deals}
TECH/PR: {tech}
NOTION: {notion}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ── SLACK POSTING ─────────────────────────────────────────────────────────────

def post_to_slack(message):
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json"
        },
        json={"channel": GUSTAV_USER_ID, "text": message, "mrkdwn": True}
    )
    if r.json().get("ok"):
        print(f"[{datetime.now()}] Brief sendt til Slack!")
    else:
        print(f"[{datetime.now()}] Feil: {r.json()}")


# ── JOBS ──────────────────────────────────────────────────────────────────────

def daily_job():
    if datetime.now().weekday() < 5:  # man-fre
        print(f"[{datetime.now()}] Kjører daglig brief...")
        msg = generate_brief("daily")
        post_to_slack(msg)

def weekly_job():
    print(f"[{datetime.now()}] Kjører ukentlig brief...")
    msg = generate_brief("weekly")
    post_to_slack(msg)


# ── SCHEDULE ──────────────────────────────────────────────────────────────────

schedule.every().day.at("07:30").do(daily_job)    # daglig man-fre
schedule.every().monday.at("07:30").do(weekly_job) # ukentlig mandag

if __name__ == "__main__":
    print("Telescope Brief kjører. Venter på schedule...")
    print("Neste daglig brief: mandag-fredag 07:30")
    print("Neste ukentlig brief: mandag 07:30")
    print("(Trykk Ctrl+C for å stoppe)")

    # Test umiddelbart hvis du vil:
    # daily_job()
    # weekly_job()

    while True:
        schedule.run_pending()
        time.sleep(60)