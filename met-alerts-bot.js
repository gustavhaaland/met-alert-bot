const https = require("https");

const WEBHOOK = process.env.SLACK_WEBHOOK;
const YR_URL = "https://www.yr.no/api/v0/warnings?language=en";

const SEVERITY_EMOJI = { Extreme: "🔴", Severe: "🟠" };

const EVENT_TYPE_EMOJI = {
  Flood: "🌊", Avalanche: "🏔️", Gale: "💨", Rain: "🌧️",
  Snow: "❄️", Ice: "🧊", StormSurge: "🌊", Lightning: "⛈️",
};

function get(url) {
  return new Promise((res, rej) => {
    https.get(url, { headers: { "User-Agent": "met-alert-bot/1.0" } }, r => {
      let d = "";
      r.on("data", c => d += c);
      r.on("end", () => res(d));
      r.on("error", rej);
    }).on("error", rej);
  });
}

function post(url, body) {
  return new Promise((res, rej) => {
    const s = JSON.stringify(body);
    const u = new URL(url);
    const req = https.request({
      hostname: u.hostname, path: u.pathname, method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(s) }
    }, r => { let d = ""; r.on("data", c => d += c); r.on("end", () => res(r.statusCode)); });
    req.on("error", rej);
    req.write(s);
    req.end();
  });
}

async function main() {
  if (!WEBHOOK) throw new Error("SLACK_WEBHOOK not set");

  console.log("Fetching warnings from Yr...");
  const raw = await get(YR_URL);
  const data = JSON.parse(raw);

  const allWarnings = data.warnings || [];
  const warnings = allWarnings.filter(w =>
    w.meta.severity === "Severe" || w.meta.severity === "Extreme"
  );

  console.log(`Found ${allWarnings.length} total, ${warnings.length} severe/extreme warning(s)`);

  if (warnings.length === 0) {
    console.log("No severe alerts, skipping Slack message.");
    return;
  }

  const blocks = [
    { type: "header", text: { type: "plain_text", text: "⚠️ Norwegian Weather & Nature Warnings", emoji: true }},
    { type: "context", elements: [{ type: "mrkdwn", text: `Source: *yr.no* (MET + NVE) • ${new Date().toLocaleString("nb-NO", { timeZone: "Europe/Oslo" })}` }]},
    { type: "divider" }
  ];

  for (const w of warnings.slice(0, 15)) {
    const { shortTitle, severity, eventType, areas, label } = w.meta;
    const sevEmoji = SEVERITY_EMOJI[severity] || "⚠️";
    const typeEmoji = EVENT_TYPE_EMOJI[eventType] || "🌍";
    const areaText = areas?.join(", ") || "Unknown area";
    const categoryLabel = label ? ` · _${label}_` : "";
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: `${sevEmoji}${typeEmoji} *${shortTitle}*\n📍 ${areaText}${categoryLabel}` }
    });
    blocks.push({ type: "divider" });
  }

  if (warnings.length > 15) {
    blocks.push({ type: "context", elements: [{ type: "mrkdwn", text: `_…and ${warnings.length - 15} more. See <https://www.yr.no/en/warnings|yr.no/warnings>._` }]});
  }

  const status = await post(WEBHOOK, { username: "Weather Alerts Norway", icon_emoji: ":warning:", blocks });
  if (status === 200) console.log("✅ Sent to Slack!");
  else throw new Error("Slack responded with status: " + status);
}

main().catch(e => { console.error(e.message); process.exit(1); });
