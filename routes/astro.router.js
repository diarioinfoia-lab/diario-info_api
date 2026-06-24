const express = require("express");
const router = express.Router();
const astroController = require("../controllers/astro.controller.js");

// GET /api/astro/horoscope/:sign
// Obtiene el horóscopo diario para un signo zodiacal específico (ej: aries, taurus, etc.)
// Este es un endpoint público.
router.get("/horoscope/:sign", [], astroController.getDailySignHoroscope);

module.exports = router;