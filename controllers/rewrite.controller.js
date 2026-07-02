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
    "Eres el editor periodistico del Diario Info de Santiago del Estero, Argentina.\n" +
    "Tu tarea es REESCRIBIR completamente esta noticia de " + (categoria || "general") + " para nuestra editorial.\n" +
    "REGLAS OBLIGATORIAS:\n" +
    "1. TITULO: Debe ser 100% original y creativo. PROHIBIDO copiar, traducir o parafrasear el titulo original. Usa un enfoque editorial propio. Maximo 100 caracteres.\n" +
    "2. COPETE (bajada): Debe ser una sintesis editorial propia. PROHIBIDO repetir frases del titulo original ni del cuerpo original. Maximo 200 caracteres.\n" +
    "3. CUERPO: Minimo 3 parrafos separados por doble salto de linea (\\n\\n). Cada parrafo debe terminar con punto. No inventar datos pero reformular todo con voz propia. Minimo 300 caracteres.\n" +
    "4. El cuerpo NO debe ser un texto continuo sin pausas. Cada parrafo es una idea completa separada visualmente.\n" +
    "Responde SOLO con JSON valido sin markdown ni bloques de codigo:\n" +
    '{"titulo": "titulo editorial original", "copete": "bajada editorial propia", "cuerpo": "parrafo 1...\\n\\nparrafo 2...\\n\\nparrafo 3..."}\n\n' +
    "NOTICIA ORIGINAL (solo para extraer los hechos, no para copiar):\n" +
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


/**
 * GET /articles-hoy
 * Devuelve las 15 notas publicadas de hoy ordenadas por publicationDate DESC
 * Endpoint de diagnostico temporal
 */
exports.articulosHoy = async (req, res) => {
  try {
    const mongoose = require("mongoose");
    const db = mongoose.connection.db;
    if (!db) return res.status(500).json({ error: "No hay conexion a MongoDB" });

    const now = new Date();
    const hoyFin = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 23, 59, 59));
    const ayerInicio = new Date(hoyFin);
    ayerInicio.setUTCDate(ayerInicio.getUTCDate() - 1);
    ayerInicio.setUTCHours(0, 0, 0, 0);

    // Intento 1: published + publicationDate
    let articles = await db.collection("articles").find(
      { status: "published", publicationDate: { $gte: ayerInicio, $lte: hoyFin } }
    ).sort({ publicationDate: -1, priority: -1 }).limit(15).toArray();

    let source = "publicationDate";

    // Intento 2: published + updatedAt
    if (articles.length === 0) {
      articles = await db.collection("articles").find(
        { status: "published", updatedAt: { $gte: ayerInicio, $lte: hoyFin } }
      ).sort({ updatedAt: -1 }).limit(15).toArray();
      source = "updatedAt";
    }

    // Diagnostico: ver los 5 mas recientes de cualquier status
    const anyRecent = await db.collection("articles").find({})
      .sort({ updatedAt: -1 }).limit(5).toArray();

    const sampleKeys = anyRecent.length > 0 ? Object.keys(anyRecent[0]).join(", ") : "no docs";

    const result = articles.map((a, i) => ({
      n: i + 1,
      titulo: a.title || a.titulo || "(sin titulo)",
      publicationDate: a.publicationDate ? new Date(a.publicationDate).toISOString() : null,
      updatedAt: a.updatedAt ? new Date(a.updatedAt).toISOString() : null,
      status: a.status
    }));

    const recentAny = anyRecent.map(a => ({
      titulo: (a.title || a.titulo || "").substring(0, 60),
      status: a.status,
      publicationDate: a.publicationDate ? new Date(a.publicationDate).toISOString() : null,
      updatedAt: a.updatedAt ? new Date(a.updatedAt).toISOString() : null
    }));

    return res.status(200).json({
      total: result.length,
      source: source,
      rango: { desde: ayerInicio.toISOString(), hasta: hoyFin.toISOString() },
      articulos: result,
      schemaKeys: sampleKeys,
      ultimos5Cualquier: recentAny
    });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
