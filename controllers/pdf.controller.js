const { spawn } = require('child_process');
const path = require('path');

const SCRIPT_PATH = process.env.PDF_SCRIPT_PATH || '/home/diarioin/scripts/genera_diario_pdf.py';
const PYTHON_BIN  = process.env.PYTHON_BIN  || 'python3';
const PDF_SECRET  = process.env.PDF_SECRET   || 'diarioinfo-pdf-secret-2024';

exports.generarPdf = async (req, res) => {
  // Verificacion del token secreto
  const token = req.headers['x-pdf-secret'] || req.body.secret;
  if (token !== PDF_SECRET) {
    return res.status(401).json({ ok: false, message: 'No autorizado' });
  }

  console.log('[PDF] Iniciando generacion de diario...');
  const inicio = Date.now();

  // Respuesta inmediata: el proceso puede tardar varios minutos
  res.json({
    ok: true,
    message: 'Generacion de PDF iniciada. El archivo estara disponible en pocos minutos.',
    script: SCRIPT_PATH,
  });

  // Ejecutar el script Python en background
  const proc = spawn(PYTHON_BIN, [SCRIPT_PATH], {
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  proc.stdout.on('data', (data) => {
    console.log('[PDF stdout]', data.toString().trim());
  });

  proc.stderr.on('data', (data) => {
    console.error('[PDF stderr]', data.toString().trim());
  });

  proc.on('close', (code) => {
    const seg = ((Date.now() - inicio) / 1000).toFixed(1);
    if (code === 0) {
      console.log(`[PDF] Completado OK en ${seg}s`);
    } else {
      console.error(`[PDF] Error - exit code ${code} en ${seg}s`);
    }
  });

  proc.unref();
};
