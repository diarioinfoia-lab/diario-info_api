<?php
// generar_pdf.php - Trigger manual de generacion del diario
// Subir a: /home/diarioin/public_html/generar-pdf.php
// Acceso:  https://diarioinfo.com/generar-pdf.php?secret=diarioinfo-pdf-2024

define('SECRET', 'diarioinfo-pdf-2024');
define('SCRIPT', '/home/diarioin/scripts/genera_diario_pdf.py');
define('PYTHON', '/usr/bin/python3');
define('LOG',    '/home/diarioin/logs/genera_pdf.log');

header('Content-Type: text/html; charset=utf-8');

// Verificar secret
$secret = $_GET['secret'] ?? '';
if ($secret !== SECRET) {
    http_response_code(401);
    echo '<h2 style="font-family:sans-serif;color:red">No autorizado</h2>';
    exit;
}

// Verificar que el script existe
if (!file_exists(SCRIPT)) {
    http_response_code(500);
    echo '<h2 style="font-family:sans-serif;color:red">Error: script no encontrado en ' . SCRIPT . '</h2>';
    exit;
}

// Crear directorio de logs si no existe
$log_dir = dirname(LOG);
if (!is_dir($log_dir)) {
    mkdir($log_dir, 0755, true);
}

// Ejecutar en background (no bloquea la respuesta)
$cmd = PYTHON . ' ' . SCRIPT . ' >> ' . LOG . ' 2>&1 &';
shell_exec($cmd);

// Respuesta HTML
?>
<!DOCTYPE html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>DiarioInfo - Generar PDF</title>
  <style>
    body { font-family: Arial, sans-serif; text-align: center; padding: 60px 20px; background: #f0f4ff; }
    .card { background: white; border-radius: 12px; padding: 40px; max-width: 500px;
            margin: 0 auto; box-shadow: 0 4px 20px rgba(0,0,0,.1); }
    h1 { color: #003399; margin-bottom: 10px; }
    p  { color: #444; line-height: 1.6; }
    .btn { display: inline-block; margin-top: 20px; padding: 12px 24px;
           background: #003399; color: white; border-radius: 8px;
           text-decoration: none; font-weight: bold; }
    .btn:hover { background: #002277; }
    .info { background: #eef2ff; border-radius: 8px; padding: 12px;
            font-size: 13px; color: #555; margin-top: 20px; }
  </style>
</head>
<body>
  <div class='card'>
    <h1>&#x2705; Generacion iniciada</h1>
    <p>El script esta corriendo en el servidor.<br>
       El PDF del diario estara listo en <strong>2-5 minutos</strong>.</p>
    <a class='btn' href='https://diarioinfo.com/revistas/diarioinfo/' target='_blank'>
      Ver diario publicado
    </a>
    <div class='info'>
      Hora de inicio: <?php echo date('d/m/Y H:i:s'); ?><br>
      Log: <?php echo LOG; ?>
    </div>
  </div>
</body>
</html>
