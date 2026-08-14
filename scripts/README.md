# Agregador de Noticias DiarioInfo

## Instalacion Manual (desde terminal cPanel)

### 1. Crear directorio y descargar script
```bash
mkdir -p /home/diarioin/scripts && cd /home/diarioin/scripts
curl -s https://raw.githubusercontent.com/diarioinfoia-lab/diario-info_api/master/scripts/noticias_agregador.py > noticias_agregador.py
```

### 2. Instalar dependencias
```bash
pip3 install requests beautifulsoup4 pymongo --user
```

### 3. Configurar variables de entorno

El script YA NO trae credenciales de Mongo hardcodeadas: ambas variables son
obligatorias y si falta `MONGO_URI` el script se aborta apenas arranca (no
intenta correr sin base de datos).

```bash
export MONGO_URI="mongodb+srv://usuario:password@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
export ANTHROPIC_API_KEY="TU_API_KEY_AQUI"
```

NOTA: la variable de reescritura con IA es `ANTHROPIC_API_KEY` (el script llama a
Claude a traves de un proxy en Vercel), no `GEMINI_API_KEY` como decia antes esta
guia. Si no se configura, el script sigue publicando las notas usando el
contenido original scrapeado (sin reescritura), y las marca como "Red-info" sin
sufijo de categoria para que se note a simple vista en el panel.

### 4. Ejecutar (prueba)
```bash
MONGO_URI="..." ANTHROPIC_API_KEY="TU_API_KEY" python3 /home/diarioin/scripts/noticias_agregador.py
```

### 5. Configurar cron (cada 2 horas)
```
0 */2 * * * MONGO_URI="..." ANTHROPIC_API_KEY="TU_API_KEY" python3 /home/diarioin/scripts/noticias_agregador.py >> /home/diarioin/scripts/noticias.log 2>&1
```

Tip: en cPanel/servidores compartidos, en vez de pegar las credenciales en la
linea de cron (quedan visibles en `crontab -l` y en logs del sistema), conviene
ponerlas en un archivo `.env` con permisos restringidos y cargarlas antes de
ejecutar, por ejemplo `set -a; source /home/diarioin/scripts/.env; set +a; python3 ...`.

## Fuentes configuradas
- El Liberal Policiales
- Diario Panorama Policiales
- Diario Panorama Espectaculos
- La Nacion Espectaculos
