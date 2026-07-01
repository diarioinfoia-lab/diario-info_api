const fetch = require("node-fetch");

const ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages";
ANTHROPIC_MODEL   = process.env.ANTHROPIC_MODEL || "claude-3-5-sonnet-20241022";

/**
 * POST /rewrite
 * Body: { titulo, cuerpo, categoria, apiKey }
 * Returns: { titulo, copete, cuerpo } rewritten in DiarioInfo style
 */
exports.rewrite = async (req, res) => {
  const { titulo, cuerpo, categoria, apiKey } = req.body;

  if (!titulo || !cuerpo) {
    return res.status(400).json({ error: "titulo y cuerpo son requeridos" });
  }

  const key = apiKey || process.env.ANTHROPIC_API_KEY;
  if (!key) {
    return res.status(500).json({ error: "ANTHROPIC_API_KEY no configurada" });
  }

  const prompt =
    "Eres un redactor periodistico del Diario Info de Santiago del Estero, Argentina.\n" +
    "Reescribe esta noticia de " + (categoria || "general") + " en formato periodistico profesional.\n" +
    "La nota debe ser original, no inventar datos.\n" +
    'Responde SOLO con JSON valido sin markdown: {"titulo": "max 100 chars", "copete": "max 200 chars", "cuerpo": "min 300 chars"}\n\n' +
    "NOTICIA ORIGINAL:\n" +
    "Titulo: " + titulo + "\n" +
    "Cuerpo: " + cuerpo.substring(0, 2000);

  try {
    const response = await fetch(ANTHROPIC_API_URL, {
      method: "POST",
      headers: {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: ANTHROPIC_MODEL,
        max_tokens: 1024,
        messages: [{ role: "user", content: prompt }],
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      console.error("[rewrite] Anthropic error:", JSON.stringify(data));
      return res.status(502).json({ error: "Error de Anthropic API", detail: data });
    }

    let text = data.content[0].text.trim();

    // Strip markdown code block if present
    if (text.includes("```")) {
      const parts = text.split("```");
      text = parts[1] || text;
      if (text.startsWith("json")) text = text.slice(4);
    }

    const result = JSON.parse(text.trim());
    return res.status(200).json(result);

  } catch (err) {
    console.error("[rewrite] Error:", err.message);
    return res.status(500).json({ error: err.message });
  }
};

// model: claude-3-5-sonnet-20241022
