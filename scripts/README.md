# Agregador de Noticias DiarioInfo

## Instalacion Manual (desde terminal cPanel)

### 1. Crear directorio y descargar script
```bash
mkdir -p /home/diarioin/scripts && cd /home/diarioin/scripts
curl -s https://raw.githubusercontent.com/diarioinfoia-lab/diario-info_api/master/scripts/noticias_agregador.py > noticias_agregador.py
```

### 2. Instalar dependencias
```bash
pip3 install requests beautifulsoup4 --user
```

### 3. Configurar API key de Gemini
Obtener la clave desde: https://console.cloud.google.com/apis/credentials?project=gen-lang-client-0070993322

```bash
export GEMINI_API_KEY="TU_API_KEY_AQUI"
```

NOTA: Activar facturacion en Google Cloud Console para usar la API.

### 4. Ejecutar (prueba)
```bash
GEMINI_API_KEY="TU_API_KEY" python3 /home/diarioin/scripts/noticias_agregador.py
```

### 5. Configurar cron (cada 2 horas)
```
0 */2 * * * GEMINI_API_KEY="TU_API_KEY" python3 /home/diarioin/scripts/noticias_agregador.py >> /home/diarioin/scripts/noticias.log 2>&1
```

## Fuentes configuradas
- El Liberal Policiales
- Diario Panorama Policiales
- Diario Panorama Espectaculos
- La Nacion Espectaculos