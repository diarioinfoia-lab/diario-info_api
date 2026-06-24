const express = require('express');
const router = express.Router();
const pdfController = require('../controllers/pdf.controller');

// GET  /admin/generar-pdf?secret=xxx  -> desde el navegador
router.get('/admin/generar-pdf', pdfController.generarPdfGet);

// POST /admin/generar-pdf  -> desde curl / app
router.post('/admin/generar-pdf', pdfController.generarPdf);

module.exports = router;
