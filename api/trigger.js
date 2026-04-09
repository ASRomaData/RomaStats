export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") return res.status(200).end();
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "Method not allowed" });

  const token = process.env.GITHUB_TOKEN;
  const owner = process.env.GITHUB_OWNER;
  const repo  = process.env.GITHUB_REPO;

  if (!token || !owner || !repo) {
    return res.status(500).json({
      ok: false,
      error: "Configura GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO nelle variabili Vercel."
    });
  }

  const force = req.body?.force === "true" ? "true" : "false";

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/bot.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization:        `Bearer ${token}`,
        Accept:               "application/vnd.github+json",
        "Content-Type":       "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main", inputs: { force } }),
    }
  );

  if (response.ok || response.status === 204) {
    return res.status(200).json({
      ok: true,
      message: "Workflow avviato! Attendi 30-60 secondi e ricarica."
    });
  }

  const err = await response.text();
  return res.status(response.status).json({ ok: false, error: err });
}
