/**
 * astro.controller.js
 * ─────────────────────────────────────────────────────────────────
 * Daily horoscope controller by sign, 100% in Spanish.
 * * IT EXACTLY SIMULATES THE NATIVE STRUCTURE OF THE V1 API:
 * {
 * "meta": { ... },
 * "data": { ... }
 * }
 * ─────────────────────────────────────────────────────────────────
 */
const axios = require("axios");

const API_BASE_URL = "https://api.freeastroapi.com/api/v2";
const API_KEY = process.env.FREEASTROAPI_KEY;
const DEFAULT_TZ = "America/Argentina/Buenos_Aires";
const REQUEST_TIMEOUT_MS = 8000;

// ─────────────────────────────────────────────────────────────────
// SPANISH DICTIONARIES
// ─────────────────────────────────────────────────────────────────

const ZODIAC_SIGNS_ES = {
  aries: "Aries",
  taurus: "Tauro",
  gemini: "Géminis",
  cancer: "Cáncer",
  leo: "Leo",
  virgo: "Virgo",
  libra: "Libra",
  scorpio: "Escorpio",
  sagittarius: "Sagitario",
  capricorn: "Capricornio",
  aquarius: "Acuario",
  pisces: "Piscis",
};

const VALID_SIGNS = Object.keys(ZODIAC_SIGNS_ES);

const COLOR_TRANSLATION = {
  red: "Rojo", blue: "Azul", green: "Verde", yellow: "Amarillo",
  white: "Blanco", black: "Negro", purple: "Violeta", violet: "Violeta",
  gold: "Dorado", silver: "Plateado", orange: "Naranja", turquoise: "Turquesa",
  pink: "Rosa", brown: "Marrón",
};

const MOON_PHASE_TRANSLATION = {
  new_moon: "Luna Nueva",
  waxing_crescent: "Luna Creciente",
  first_quarter: "Cuarto Creciente",
  waxing_gibbous: "Gibosa Creciente",
  full_moon: "Luna Llena",
  waning_gibbous: "Gibosa Menguante",
  last_quarter: "Cuarto Menguante",
  waning_crescent: "Luna Menguante",
};

const ASPECT_TRANSLATION = {
  conjunction: "Conjunción",
  sextile: "Sextil",
  square: "Cuadratura",
  trine: "Trígono",
  opposition: "Oposición",
};

// ─────────────────────────────────────────────────────────────────
// CONTENT BANKS FOR STATIC MODE (all in Spanish)
// ─────────────────────────────────────────────────────────────────

const THEMES_POOL = [
  "Iniciativa", "Estabilidad", "Comunicación", "Sensibilidad", "Liderazgo",
  "Perfeccionismo", "Equilibrio", "Intensidad", "Aventura", "Disciplina",
  "Innovación", "Intuición", "Renovación", "Constancia", "Apertura",
];

const KEYWORDS_POOL = [
  "Energía", "Foco", "Conexión", "Calma", "Crecimiento", "Confianza",
  "Claridad", "Pasión", "Paciencia", "Curiosidad", "Determinación",
  "Armonía", "Audacia", "Sensatez", "Inspiración", "Motivación",
];
const LUCKY_COLORS_POOL = [
  { key: "rojo", label: "Rojo" },
  { key: "azul", label: "Azul" },
  { key: "verde", label: "Verde" },
  { key: "amarillo", label: "Amarillo" },
  { key: "blanco", label: "Blanco" },
  { key: "violeta", label: "Violeta" },
  { key: "dorado", label: "Dorado" },
  { key: "plateado", label: "Plateado" },
  { key: "naranja", label: "Naranja" },
  { key: "turquesa", label: "Turquesa" },
];

const TIME_WINDOWS_POOL = [
  "08:00 - 11:00", "09:00 - 12:00", "10:00 - 13:00", "12:00 - 15:00",
  "14:00 - 17:00", "16:00 - 19:00", "18:00 - 21:00", "20:00 - 23:00",
];

const OPENING_LINES_POOL = [
  (s) => `Hoy ${s} atraviesa un día marcado por la necesidad de poner en orden las prioridades.`,
  (s) => `La energía del día invita a ${s} a moverse con más decisión de lo habitual.`,
  (s) => `Para ${s}, la jornada trae una mezcla de introspección y ganas de avanzar.`,
  (s) => `${s} encuentra hoy una oportunidad para mostrar su lado más auténtico.`,
];

const DEVELOPMENT_LINES_POOL = [
  "En el plano afectivo conviene priorizar la honestidad por sobre la urgencia de resolver todo de inmediato.",
  "En lo laboral, ordenar tareas pequeñas antes que las grandes va a aliviar bastante la cabeza.",
  "El dinero pide atención: no es un buen día para gastos impulsivos ni decisiones financieras apuradas.",
  "La salud responde bien al descanso; el cuerpo está pidiendo bajar un poco el ritmo.",
];

const DO_ITEMS_POOL = [
  "Confiar en la intuición", "Tomar las cosas con calma", "Organizar las prioridades", "Compartir las ideas propias",
];

const DONT_ITEMS_POOL = [
  "Sobrepensar cada detalle", "Tomar decisiones apuradas", "Discutir por algo menor", "Postergar tareas importantes",
];

// ─────────────────────────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────────────────────────

function resolveDate(dateParam, tzStr) {
  let dateObj;
  if (!dateParam || String(dateParam).toLowerCase() === "today") {
    dateObj = new Date();
  } else if (/^\d{4}-\d{2}-\d{2}$/.test(String(dateParam))) {
    dateObj = new Date(`${dateParam}T12:00:00Z`);
    if (Number.isNaN(dateObj.getTime())) dateObj = new Date();
  } else {
    dateObj = new Date();
  }

  let iso;
  try {
    iso = new Intl.DateTimeFormat("en-CA", {
      timeZone: tzStr || DEFAULT_TZ,
      year: "numeric", month: "2-digit", day: "2-digit",
    }).format(dateObj);
  } catch (e) {
    iso = dateObj.toISOString().slice(0, 10);
  }
  return { iso, dateObj };
}

function hashText(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return hash;
}

function createSeededRandom(seedStr) {
  let seed = hashText(seedStr) | 0;
  return function rng() {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randomInt(rng, min, max) { return Math.floor(rng() * (max - min + 1)) + min; }
function chooseOne(rng, list) { return list[Math.floor(rng() * list.length)]; }
function chooseSeveral(rng, list, quantity) {
  const listCopy = [...list]; const result = [];
  for (let i = 0; i < quantity && listCopy.length > 0; i++) {
    const idx = Math.floor(rng() * listCopy.length);
    result.push(listCopy.splice(idx, 1)[0]);
  }
  return result;
}

function calculateMoonPhase(dateObj) {
  const CICLO_SINODICO = 29.530588853;
  const LUNA_NUEVA_REF = new Date("2000-01-06T18:14:00Z").getTime();
  const diasDesdeRef = (dateObj.getTime() - LUNA_NUEVA_REF) / 86400000;
  let fraccion = (diasDesdeRef % CICLO_SINODICO) / CICLO_SINODICO;
  if (fraccion < 0) fraccion += 1;

  const fases = [
    { hasta: 0.0625, key: "new_moon", label: "Luna Nueva" },
    { hasta: 0.1875, key: "waxing_crescent", label: "Luna Creciente" },
    { hasta: 0.3125, key: "first_quarter", label: "Cuarto Creciente" },
    { hasta: 0.4375, key: "waxing_gibbous", label: "Gibosa Creciente" },
    { hasta: 0.5625, key: "full_moon", label: "Luna Llena" },
    { hasta: 0.6875, key: "waning_gibbous", label: "Gibosa Menguante" },
    { hasta: 0.8125, key: "last_quarter", label: "Cuarto Menguante" },
    { hasta: 0.9375, key: "waning_crescent", label: "Luna Menguante" },
    { hasta: 1.0, key: "new_moon", label: "Luna Nueva" },
  ];
  return fases.find((f) => fraccion <= f.hasta) || fases[fases.length - 1];
}

// ─────────────────────────────────────────────────────────────────
// NATIVE V1 LEGACY STYLE FORMATTERS (All translated)
// ─────────────────────────────────────────────────────────────────

function translateColor(colorObj) {
  if (!colorObj) return null;
  const key = (colorObj.key || "").toLowerCase();
  return { key, label: COLOR_TRANSLATION[key] || colorObj.label || key };
}

function translateMoonPhase(phaseObj, fallbackDate) {
  if (phaseObj && phaseObj.key) {
    const key = phaseObj.key.toLowerCase();
    return { key, label: MOON_PHASE_TRANSLATION[key] || phaseObj.label };
  }
  return calculateMoonPhase(fallbackDate);
}

function translateSign(signKey) {
  const key = (signKey || "").toLowerCase();
  return { key, label: ZODIAC_SIGNS_ES[key] || signKey };
}

function translateHighlight(h) {
  if (!h) return h;
  if (h.type === "moon_sign") {
    return { ...h, label: `Luna en ${ZODIAC_SIGNS_ES[h.key.toLowerCase()] || h.label}` };
  }
  if (h.type === "sky_aspect" && typeof h.key === "string") {
    const partes = h.key.split("_");
    if (partes.length === 3) {
      const aspecto = ASPECT_TRANSLATION[partes[1]] || partes[1];
      return { ...h, label: `${capitalize(partes[0])} ${aspecto} ${capitalize(partes[2])}` };
    }
  }
  return h;
}

function capitalize(str) { return str ? str.charAt(0).toUpperCase() + str.slice(1) : str; }

/**
 * Normalizes the live API response, adapting it EXACTLY
 * to the V1 API JSON schema.
 */
function normalizeLiveResponse(apiData, signKey, isoDate, dateObj) {
  const responseData = apiData?.data || {};
  const scores = responseData.scores || {};
  const content = responseData.content || {};
  const lucky = responseData.lucky || {};
  const astro = responseData.astro || {};

  const rng = createSeededRandom(`${signKey}-${isoDate}-filler`);

  const textoFinal = content.text && content.text.trim().length > 0
    ? content.text
    : `${chooseOne(rng, OPENING_LINES_POOL)(ZODIAC_SIGNS_ES[signKey])} ${chooseOne(rng, DEVELOPMENT_LINES_POOL)}`;

  const moonPhase = translateMoonPhase(astro.moon_phase, dateObj);
  const moonSign = astro.moon_sign ? translateSign(astro.moon_sign.key) : translateSign(chooseOne(rng, VALID_SIGNS));

  return {
    meta: {
      request_id: apiData?.meta?.request_id || `req_${hashText(signKey + isoDate).toString(16)}`,
      generated_at: apiData?.meta?.generated_at || new Date().toISOString().split(".")[0],
      settings: {
        timezone: apiData?.meta?.settings?.timezone || DEFAULT_TZ,
        locale: "es",
        date_resolved: isoDate,
        version: "v1"
      },
      engine: { name: "DailyHoroscopeEngine", version: "1.0.0" }
    },
    data: {
      sign: signKey,
      date: isoDate,
      scores: {
        overall: scores.overall ?? randomInt(rng, 55, 95),
        love: scores.love ?? randomInt(rng, 55, 95),
        career: scores.career ?? randomInt(rng, 55, 95),
        money: scores.money ?? randomInt(rng, 55, 95),
        health: scores.health ?? randomInt(rng, 55, 95),
      },
      lucky: {
        color: translateColor(lucky.color) || chooseOne(rng, LUCKY_COLORS_POOL),
        number: lucky.number ?? randomInt(rng, 1, 99),
        time_window: lucky.time_window || chooseOne(rng, TIME_WINDOWS_POOL),
      },
      content: {
        text: textoFinal,
        theme: content.theme || chooseOne(rng, THEMES_POOL),
        keywords: content.keywords && content.keywords.length > 0 ? content.keywords : chooseSeveral(rng, KEYWORDS_POOL, 2),
        do: content.do && content.do.length > 0 ? content.do : chooseSeveral(rng, DO_ITEMS_POOL, 2),
        dont: content.dont && content.dont.length > 0 ? content.dont : chooseSeveral(rng, DONT_ITEMS_POOL, 2),
      },
      astro: {
        moon_sign: moonSign,
        moon_phase: moonPhase,
        highlights: Array.isArray(astro.highlights) && astro.highlights.length > 0
          ? astro.highlights.map(translateHighlight)
          : [
            { type: "moon_sign", key: moonSign.key, label: `Luna en ${moonSign.label}` },
            { type: "moon_phase", key: moonPhase.key, label: moonPhase.label }
          ],
      },
    },
  };
}

/**
 * Deterministic static generator that EXACTLY clones the V1 API JSON schema.
 */
function buildStaticHoroscope(signKey, isoDate, dateObj) {
  const rng = createSeededRandom(`${signKey}-${isoDate}`);
  const signLabel = ZODIAC_SIGNS_ES[signKey] || signKey;

  const love = randomInt(rng, 55, 99);
  const career = randomInt(rng, 50, 95);
  const money = randomInt(rng, 45, 95);
  const health = randomInt(rng, 55, 99);
  const overall = Math.round((love + career + money + health) / 4);

  const opening = chooseOne(rng, OPENING_LINES_POOL)(signLabel);
  const development = chooseOne(rng, DEVELOPMENT_LINES_POOL);

  const moonPhase = calculateMoonPhase(dateObj);
  const moonSignKey = chooseOne(rng, VALID_SIGNS);
  const moonSignLabel = ZODIAC_SIGNS_ES[moonSignKey];

  return {
    meta: {
      request_id: `req_${hashText(signKey + isoDate).toString(16)}`,
      generated_at: new Date().toISOString().split(".")[0],
      settings: { timezone: DEFAULT_TZ, locale: "es", date_resolved: isoDate, version: "v1" },
      engine: { name: "DailyHoroscopeEngine", version: "1.0.0" }
    },
    data: {
      sign: signKey,
      date: isoDate,
      scores: { overall, love, career, money, health },
      lucky: {
        color: chooseOne(rng, LUCKY_COLORS_POOL),
        number: randomInt(rng, 1, 99),
        time_window: chooseOne(rng, TIME_WINDOWS_POOL),
      },
      content: {
        text: `${opening} ${development}`,
        theme: chooseOne(rng, THEMES_POOL),
        keywords: chooseSeveral(rng, KEYWORDS_POOL, 2),
        do: chooseSeveral(rng, DO_ITEMS_POOL, 2),
        dont: chooseSeveral(rng, DONT_ITEMS_POOL, 2),
      },
      astro: {
        moon_sign: { key: moonSignKey, label: moonSignLabel },
        moon_phase: { key: moonPhase.key, label: moonPhase.label },
        highlights: [
          { type: "moon_sign", key: moonSignKey, label: `Luna en ${moonSignLabel}` },
          { type: "moon_phase", key: moonPhase.key, label: moonPhase.label },
        ],
      },
    },
  };
}

// ─────────────────────────────────────────────────────────────────
// CONTROLLER PRINCIPAL
// ─────────────────────────────────────────────────────────────────

exports.getDailySignHoroscope = async (req, res) => {
  const { sign } = req.params;
  const { date, tz_str, static: staticMode } = req.query;

  const signKey = (sign || "").toLowerCase();

  if (!signKey || !VALID_SIGNS.includes(signKey)) {
    return res.status(400).json({
      meta: { error: "Bad Request" },
      data: null,
      message: "Por favor, proporciona un signo zodiacal válido."
    });
  }

  const tzStr = tz_str || DEFAULT_TZ;
  const { iso: isoDate, dateObj } = resolveDate(date, tzStr);
  const forceStatic = staticMode === "true" || staticMode === "1" || staticMode === true;

  // 1. Forced Static Case (?static=true)
  if (forceStatic) {
    const apiV1CloneJson = buildStaticHoroscope(signKey, isoDate, dateObj);
    return res.status(200).json(apiV1CloneJson);
  }

  // 2. Case with no API Key configured (Returns the API clone without failing)
  if (!API_KEY) {
    console.warn("[ASTRO] FREEASTROAPI_KEY not configured. Responding with V1 Mock.");
    const apiV1CloneJson = buildStaticHoroscope(signKey, isoDate, dateObj);
    return res.status(200).json(apiV1CloneJson);
  }

  // 3. Live attempt with the real API
  try {
    const response = await axios.get(`${API_BASE_URL}/horoscope/daily/sign`, {
      headers: { "x-api-key": API_KEY },
      params: {
        sign: signKey,
        date: date || "today",
        tz_str: tzStr,
        locale: "es",
      },
      timeout: REQUEST_TIMEOUT_MS,
    });

    // We map the live response to use EXACTLY the same V1 JSON
    const apiV1CloneJson = normalizeLiveResponse(response.data, signKey, isoDate, dateObj);
    return res.status(200).json(apiV1CloneJson);

  } catch (error) {
    // If the external API is down, we return the faithful simulation with native V1 format
    const apiV1CloneJson = buildStaticHoroscope(signKey, isoDate, dateObj);
    return res.status(200).json(apiV1CloneJson);
  }
};