<?php
// generar_pdf.php - trigger manual + ver log
define('SECRET', 'diarioinfo-pdf-2024');

header('Content-Type: text/html; charset=utf-8');
$secret = isset($_GET['secret']) ? $_GET['secret'] : '';
if ($secret !== SECRET) {
    http_response_code(401);
    echo '<h2 style="font-family:sans-serif;color:red">No autorizado</h2>'; exit;
}

$action = isset($_GET['action']) ? $_GET['action'] : 'run';

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

$log_file = '/home/diarioin/logs/genera_pdf.log';

// --- ACCION: ver log ---
if ($action === 'log') {
    echo '<html><head><meta charset="utf-8"><title>Log PDF</title>';
    echo '<style>body{font-family:monospace;background:#111;color:#0f0;padding:20px}a{color:#ff0;}h2{color:#ff0;}</style></head><body>';
    echo '<h2>Log: ' . $log_file . '</h2>';
    echo '<p><a href="?secret=' . SECRET . '">Ejecutar de nuevo</a></p>';
    if (file_exists($log_file)) {
        $log = file_get_contents($log_file);
        echo '<pre>' . htmlspecialchars($log) . '</pre>';
    } else {
        echo '<p style="color:orange">Log no existe todavia.</p>';
    }
    echo '</body></html>';
    exit;
}

// --- ACCION: ejecutar ---
echo '<html><head><meta charset="utf-8"><title>Generar PDF</title>';
echo '<style>body{font-family:sans-serif;background:#f5f5f5;padding:20px}.ok{color:green;font-weight:bold}.err{color:red;font-weight:bold}.box{background:#fff;border:1px solid #ddd;padding:15px;border-radius:8px;margin:10px 0}pre{background:#111;color:#0f0;padding:10px;overflow-x:auto;white-space:pre-wrap}a.btn{display:inline-block;margin:5px;padding:10px 20px;background:#0066cc;color:#fff;text-decoration:none;border-radius:5px}</style></head><body>';
echo '<h2>Generador de PDF - Diario Info</h2>';
echo '<div class="box">';
echo '<p><b>shell_exec:</b> ' . (function_exists('shell_exec') ? '<span class="ok">OK</span>' : '<span class="err">DESHABILITADO</span>') . '</p>';
echo '<p><b>Python:</b> ' . ($python_ok ? '<span class="ok">' . $python_ok . '</span>' : '<span class="err">NO ENCONTRADO</span>') . '</p>';
echo '<p><b>Script:</b> ' . ($script_ok ? '<span class="ok">' . $script_ok . '</span>' : '<span class="err">NO ENCONTRADO</span>') . '</p>';
echo '<p><b>whoami:</b> ' . trim(shell_exec('whoami')) . '</p>';
echo '<p><b>HOME:</b> ' . trim(shell_exec('echo $HOME')) . '</p>';
echo '</div>';

if ($python_ok && $script_ok) {
    // Crear dir de logs
    $log_dir = dirname($log_file);
    if (!is_dir($log_dir)) { mkdir($log_dir, 0755, true); }
    // Limpiar log anterior
    file_put_contents($log_file, '--- Inicio: ' . date('Y-m-d H:i:s') . "\n");
    // --- AUTO-UPDATE: descarga a /tmp y ejecuta desde ahi ---
    $github_api = 'https://api.github.com/repos/diarioinfoia-lab/diario-info_api/contents/scripts/genera_diario_pdf.py';
    $tmp_script = '/tmp/diarioinfo_genera_pdf_latest.py';
    if (file_exists($tmp_script)) @unlink($tmp_script);
    $api_resp = @file_get_contents($github_api, false, stream_context_create(['http'=>['header'=>"User-Agent: PHP-diarioinfo\r\n"]]));
    $downloaded = false;
    if ($api_resp) {
        $api_data = json_decode($api_resp, true);
        $downloaded = base64_decode(str_replace("\n","", $api_data['content']));
    }
        $written = file_put_contents($tmp_script, $downloaded);
        if ($written > 10000) {
            chmod($tmp_script, 0755);
            $script_ok = $tmp_script;
            file_put_contents($log_file, "--- AUTO-UPDATE OK: " . $written . " bytes en /tmp\n", FILE_APPEND);
        } else {
            file_put_contents($log_file, "--- AUTO-UPDATE: fallo escritura en /tmp (" . $written . " bytes)\n", FILE_APPEND);
        }
    } else {
        $co = shell_exec("curl -fsSL --max-time 20 '" . $github_raw . "' -o '" . $tmp_script . "' 2>&1");
        if (file_exists($tmp_script) && filesize($tmp_script) > 10000) {
            chmod($tmp_script, 0755);
            $script_ok = $tmp_script;
            file_put_contents($log_file, "--- AUTO-UPDATE via curl OK: " . filesize($tmp_script) . " bytes en /tmp\n", FILE_APPEND);
        } else {
            file_put_contents($log_file, "--- AUTO-UPDATE FALLO: usando script local " . $script_ok . "\n", FILE_APPEND);
        }
    }
    // --- FIN AUTO-UPDATE ---
    
    $cmd = $python_ok . ' ' . $script_to_run . ' >> ' . $log_file . ' 2>&1';
    echo '<div class="box">';
    echo '<p class="ok">Ejecutando script... (puede tardar 30-60 seg)</p>';
    echo '<p><b>Comando:</b> <code>' . htmlspecialchars($cmd) . '</code></p>';
    echo '</div>';
    
    // Ejecutar sincronico
    @ob_flush(); @flush();
    shell_exec($cmd);
    
    // Mostrar log
    echo '<div class="box">';
    echo '<h3>Log de ejecucion:</h3>';
    if (file_exists($log_file)) {
        $log_content = file_get_contents($log_file);
        echo '<pre>' . htmlspecialchars($log_content) . '</pre>';
    } else {
        echo '<p style="color:orange">No se genero archivo de log.</p>';
    }
    echo '</div>';
    
    // Verificar PDF
    $today = date('Y-m-d');
    $pdf_path = '/home/diarioin/public_html/revistas/diarioinfo/' . $today . '.pdf';
    echo '<div class="box">';
    if (file_exists($pdf_path)) {
        $size = round(filesize($pdf_path)/1024, 1);
        echo '<p class="ok">PDF CREADO (' . $size . ' KB): <a href="https://diarioinfo.com/revistas/diarioinfo/' . $today . '.pdf" target="_blank" class="btn">Ver PDF de hoy</a></p>';
    } else {
        echo '<p class="err">PDF NO ENCONTRADO en: ' . $pdf_path . '</p>';
        echo '<p>Revisa el log de arriba para ver el error.</p>';
    }
    echo '</div>';
} else {
    echo '<div class="box"><p class="err">No se puede ejecutar: Python o script no encontrado.</p></div>';
}

echo '<a href="?secret=' . SECRET . '" class="btn">Ejecutar de nuevo</a>';
echo '<a href="?secret=' . SECRET . '&action=log" class="btn">Ver log completo</a>';
echo '</body></html>';
?>
