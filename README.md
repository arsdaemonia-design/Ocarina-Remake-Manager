# Ocarina Remake Manager · Hyrule Archive Edition

Gestor de partidas, perfiles globales y mods para **Hookshot**, **Longshot** y **NX2NAVI** construido con **Python** y **PySide6 (Qt Widgets)**, con interfaz bilingüe (**Español / English**).

---

## Características principales

- **Ports soportados**:
  - **Hookshot** (`RomFS`, perfiles de partida y mods)
  - **Longshot** (`RomFS`, perfiles de partida y mods)
  - **NX2NAVI** (`RomFS` / `ExeFS`, transacciones `save-tx`, lectura de `nx2navi.ini` y logs `Not Usable`)
- **Perfil global unificado**: cambia de usuario y aplica sus **partidas** y **mods** vinculados en un solo clic (con respaldo automático previo), o desvincula ambos si prefieres perfiles separados.
- **Inicio limpio (Día 1)**: el ejecutable es completamente portable. Si no existe `settings.json`, abre directamente en **Configuración** para que selecciones las carpetas de tus ports y genera `Mods/`, `backups/`, `settings.json` y `operations.log` junto a él automáticamente.
- **Partidas e Inventario real**:
  - Tarjetas visuales de `slot_00..slot_05` con captura extraída de `caption.sav`, escena, corazones, rupias, magia, Skulltulas, fecha y coordenadas.
  - Decodificación completa de `progress.sav` (espadas, escudos, túnicas, botas, Piedras Espirituales, Medallones, objetos/magias, mejoras, botellas con contenido, piezas de corazón y munición).
  - Respaldar, exportar, restaurar slots e **Importar save…** desde volcados de emulador o carpetas de slot sueltas a un perfil nuevo.
- **Gestión avanzada de Mods**:
  - Biblioteca central en `Mods/` con importación desde `.zip`.
  - Descarga y actualización directa mediante **API pública de GameBanana** (`GameBanana URL…` con enlace o ID numérico).
  - **Detector de conflictos `RomFS`** entre mods activos y ordenación por columnas haciendo clic en los encabezados (`Mod`, `Tipo`, `Estado`).
- **Operaciones seguras en segundo plano**: barra de progreso, registro de actividad (`operations.log`) y bloqueo de escritura si el juego o launcher está abierto.

---

## Instalación y uso (Releases)

### Windows
1. Descarga **`OcarinaRemakeManager.exe`** desde la sección [Releases](../../releases).
2. Colócalo en la carpeta que prefieras y ábrelo (es un ejecutable único, no requiere carpetas extra ni instalar Python).
3. En el primer arranque, elige la carpeta de **Hookshot**, **Longshot** o **NX2NAVI** en **Configuración** (o con el botón de carpeta en **PORT ACTIVO**).

### Linux
1. Descarga **`OcarinaRemakeManager-Linux-x64.tar.gz`** desde [Releases](../../releases), extráelo y ejecuta:
   ```bash
   chmod +x OcarinaRemakeManager-Linux-x64
   ./OcarinaRemakeManager-Linux-x64
   ```
   *(Si el port elegido usa un binario `.exe` de Windows, **Jugar** intentará lanzarlo automáticamente con `wine`.)*

---

## Ejecutar o compilar desde código fuente

Requiere **Python 3.10+** (probado en Python 3.14) y las dependencias de [`requirements.txt`](requirements.txt) (`PySide6-Essentials`, `Pillow`):

```bash
pip install -r requirements.txt
python app.py
```

En Linux también puedes usar el lanzador incluido:

```bash
chmod +x run_linux.sh
./run_linux.sh
```

Para compilar un binario único (`--onefile`):
- **Linux**: `./build_linux.sh` (requiere `pyinstaller` y librerías Qt de escritorio).
- **GitHub Actions**: el workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) compila automáticamente Windows y Linux bajo demanda (`workflow_dispatch`) o al publicar un tag `v*`.

---

## Agradecimientos

- Catálogo de hashes de `progress.sav` basado en [Traiver/OOT-SW2SE](https://github.com/Traiver/OOT-SW2SE) (licencia MIT).
