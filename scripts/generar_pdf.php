<?php
// generar_pdf.php - con diagnostico completo
define('SECRET', 'diarioinfo-pdf-2024');

header('Content-Type: text/html; charset=utf-8');
$secret = isset($_GET['secret']) ? $_GET['secret'] : '';
if ($secret !== SECRET) {
    http_response_code(401);
    echo '<h2 style="font-family:sans-serif;color:red">No autorizado</h2>'; exit;
}

// --- DIAGNOSTICO ---
$python_paths = array('/usr/bin/python3','/usr/local/bin/python3','/usr/bin/python','/usr/local/bin/python');
$script_paths = array(
    '/home/diarioin/scripts/genera_diario_pdf.py',
    '/home/diarioin/public_html/scripts/genera_diario_pdf.py'
);

$python_ok = '';
foreach ($python_paths as $p) {
    if (file_exists($p)) { $python_ok = $p; break; }
}

$script_ok = '';
foreach ($script_paths as $s) {
    if (file_exists($s)) { $script_ok = $s; break; }
}

$shell_ok = function_exists('shell_exec') && !in_array('shell_exec', array_map('trim', explode(',', ini_get('disable_functions'))));

echo '<style>body{font-family:monospace;padding:20px} .ok{color:green} .err{color:red}</style>';
echo '<h2>Diagnostico</h2>';
echo '<b>shell_exec:</b> ' . ($shell_ok ? '<span class=ok>OK</span>' : '<span class=err>DESHABILITADO</span>') . '<br>';
echo '<b>Python:</b> ' . ($python_ok ? '<span class=ok>'.$python_ok.'</span>' : '<span class=err>NO ENCONTRADO</span>') . '<br>';
echo '<b>Script:</b> ' . ($script_ok ? '<span class=ok>'.$script_ok.'</span>' : '<span class=err>NO ENCONTRADO</span>') . '<br>';

// Mostrar directorio home real
$whoami = shell_exec('whoami');
$home   = shell_exec('echo $HOME');
$ls     = shell_exec('ls /home/');
echo '<b>whoami:</b> ' . htmlspecialchars(trim($whoami)) . '<br>';
echo '<b>HOME:</b> ' . htmlspecialchars(trim($home)) . '<br>';
echo '<b>ls /home/:</b> ' . htmlspecialchars(trim($ls)) . '<br>';

if (!$shell_ok) { echo '<p class=err>shell_exec deshabilitado. No se puede correr Python desde PHP.</p>'; exit; }
if (!$python_ok) { echo '<p class=err>Python no encontrado. Revisa rutas.</p>'; exit; }
if (!$script_ok) { echo '<p class=err>Script Python no encontrado. Revisa ruta.</p>'; exit; }

// --- EJECUTAR ---
$log = '/home/diarioin/logs/genera_pdf.log';
$log_dir = dirname($log);
if (!is_dir($log_dir)) mkdir($log_dir, 0755, true);
$cmd = $python_ok . ' ' . $script_ok . ' > ' . $log . ' 2>&1 &';
shell_exec($cmd);
echo '<p class=ok><b>Script lanzado!</b><br>Comando: ' . htmlspecialchars($cmd) . '</p>';
echo '<p>Revisa el log en: ' . $log . '</p>';
?>
