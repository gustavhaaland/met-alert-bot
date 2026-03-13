const https = require("https");
const { parseString } = require("xml2js");

const WEBHOOK = process.env.SLACK_WEBHOOK;
const RSS_URL = "https://api.met.no/weatherapi/metalerts/2.0/current.rss";
const EMOJI = { Extreme: "🔴", Severe: "🟠", Moderate: "🟡", Minor: "🟢" };

function get(url) {
  return new Promise((res, rej) => {
    https.get(url, r => {
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
  const xml = await get(RSS_URL);
  parseString(xml, async (err, result) => {
    if (err) throw err;
    const items = result?.rss?.channel?.[0]?.item || [];
    console.log("Found " + items.length + " alert(s)");
    const blocks = [
      { type: "header", text: { type: "plain_text", text: "MET Farevarslinger", emoji: true }},
      { type: "divider" }
    ];
    if (items.length === 0) {
      blocks.push({ type: "section", text: { type: "mrkdwn", text: "Ingen aktive farevarslinger." }});
    } else {
      for (const item of items.slice(0, 10)) {
        const title = item.title?.[0] || "Ukjent";
        const desc = (item.description?.[0] || "").replace(/<[^>]+>/g, "").slice(0, 200);
        blocks.push({ type: "section", text: { type: "mrkdwn", text: "* " + title + "*\n" + desc }});
        blocks.push({ type: "divider" });
      }
    }
    const status = await post(WEBHOOK, { username: "MET Farevarsler", icon_emoji: ":warning:", blocks });
    if (status === 200) console.log("Sendt til Slack!");
    else throw new Error("Slack status: " + status);
  });
}

main().catch(e => { console.error(e.message); process.exit(1); });
