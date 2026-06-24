const { spawn } = require('child_process');

const SCRIPT_PATH = process.env.PDF_SCRIPT_PATH || '/home/diarioin/scripts/genera_diario_pdf.py';
const PYTHON_BIN  = process.env.PYTHON_BIN  || 'python3';
const PDF_SECRET  = process.env.PDF_SECRET   || 'diarioinfo-pdf-2024';

const ejecutarScript = () => {
  const inicio = Date.now();
  console.log('[PDF] Iniciando generacion...');

  const proc = spawn(PYTHON_BIN, [SCRIPT_PATH], {
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  proc.stdout.on('data', (d) => console.log('[PDF]', d.toString().trim()));
  proc.stderr.on('data', (d) => console.error('[PDF err]', d.toString().trim()));
  proc.on('close', (code) => {
    const seg = ((Date.now() - inicio) / 1000).toFixed(1);
    console.log(`[PDF] Finalizado con codigo ${code} en ${seg}s`);
  });
  proc.unref();
};

// POST /admin/generar-pdf  (header x-pdf-secret o body.secret)
exports.generarPdf = async (req, res) => {
  const token = req.headers['x-pdf-secret'] || req.body.secret || req.query.secret;
  if (token !== PDF_SECRET) {
    return res.status(401).json({ ok: false, message: 'No autorizado' });
  }
  ejecutarScript();
  res.json({ ok: true, message: 'Generacion iniciada. El PDF estara listo en pocos minutos.' });
};

// GET /admin/generar-pdf?secret=xxx  (para usar desde el navegador)
exports.generarPdfGet = async (req, res) => {
  const token = req.query.secret;
  if (token !== PDF_SECRET) {
    return res.status(401).send('<h2>No autorizado</h2>');
  }
  ejecutarScript();
  res.send(`
    <html><head><meta charset='utf-8'>
    <style>body{font-family:Arial,sans-serif;text-align:center;padding:60px;background:#f0f4ff}
    h1{color:#003399}p{color:#444}a{color:#003399}</style></head>
    <body>
    <h1>✅ Generacion iniciada</h1>
    <p>El PDF del diario estara listo en pocos minutos.</p>
    <p><a href='https://diarioinfo.com/revistas/diarioinfo/' target='_blank'>Ver diario publicado</a></p>
    </body></html>
  `);
};
