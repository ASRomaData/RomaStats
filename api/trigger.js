module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") return res.status(200).end();
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "Method not allowed" });

  const token = process.env.GH_TOKEN;
  const owner = process.env.GH_OWNER;
  const repo  = process.env.GH_REPO;

  if (!token || !owner || !repo) {
    const missing = [
      !token && "GH_TOKEN",
      !owner && "GH_OWNER",
      !repo  && "GH_REPO",
    ].filter(Boolean).join(", ");
    return res.status(500).json({ ok: false, error: `Variabili mancanti in Vercel: ${missing}` });
  }

  // Support both old {force:"true"} and new {mode:"force"|"halftime"|"auto"}
  let mode = req.body?.mode || "auto";
  if (req.body?.force === "true") mode = "force";   // backward compat

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/bot.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization:          `Bearer ${token}`,
        Accept:                 "application/vnd.github+json",
        "Content-Type":         "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main", inputs: { mode } }),
    }
  );

  if (response.ok || response.status === 204) {
    const labels = { force: "forzata", halftime: "intervallo", auto: "automatica" };
    return res.status(200).json({
      ok: true,
      message: `Workflow avviato (modalità ${labels[mode] || mode})! Attendi 30-60 secondi e ricarica.`
    });
  }

  const err = await response.text();
  return res.status(response.status).json({ ok: false, error: err });
};
