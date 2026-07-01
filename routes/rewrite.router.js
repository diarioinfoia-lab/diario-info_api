const express = require("express");
const router = express.Router();
const rewriteController = require("../controllers/rewrite.controller");

// POST /rewrite
// Body: { titulo, cuerpo, categoria, apiKey }
router.post("/rewrite", rewriteController.rewrite);

module.exports = router;
