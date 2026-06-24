const express = require('express');
const router = express.Router();
const pdfController = require('../controllers/pdf.controller');

// POST /admin/generar-pdf
// Header requerido: x-pdf-secret: <PDF_SECRET>
// O body: { secret: '<PDF_SECRET>' }
router.post('/admin/generar-pdf', pdfController.generarPdf);

module.exports = router;
