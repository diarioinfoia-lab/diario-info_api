const express = require("express");
const router = express.Router();
const rewriteController = require("../controllers/rewrite.controller");

// POST /rewrite
// Body: { titulo, cuerpo, categoria, apiKey }
router.post("/rewrite", rewriteController.rewrite);

router.get("/articles-hoy", rewriteController.articulosHoy);

module.exports = router;
