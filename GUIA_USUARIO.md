# Guía de Usuario — Ocarina Remake Manager

Bienvenido a **Ocarina Remake Manager (Hyrule Archive Edition)**, el gestor de partidas, perfiles y mods para **Hookshot**, **Longshot** y **NX2NAVI**.

---

## 1. Instalación y primer arranque (Día 1)

### Windows
1. Descarga **`OcarinaRemakeManager.exe`** y colócalo en la carpeta que prefieras (por ejemplo `C:\Juegos\OcarinaRemakeManager\`).
2. Ábrelo con doble clic. Es un ejecutable independiente: **no necesitas carpetas adicionales ni instalar Python**.
3. En la primera ejecución verás la pantalla de **Configuración** y el selector inferior **PORT ACTIVO** mostrará `— Seleccionar carpeta de port (📁) —`.
4. Pulsa **Explorar…** (en **Configuración**) o el botón de carpeta **📁** (abajo a la izquierda) y elige la carpeta raíz de tu port (**Hookshot**, **Longshot** o **NX2NAVI**).
5. El programa creará automáticamente junto al ejecutable:
   - `Mods/` (tu biblioteca central de mods)
   - `backups/` (respaldos automáticos)
   - `settings.json` (tu configuración local)
   - `operations.log` (registro de operaciones)

### Linux
1. Descarga **`OcarinaRemakeManager-Linux-x64.tar.gz`** (o el paquete de código fuente), extráelo y ejecuta:
   ```bash
   chmod +x OcarinaRemakeManager-Linux-x64
   ./OcarinaRemakeManager-Linux-x64
   ```
2. Al igual que en Windows, creará `Mods/`, `backups/`, `settings.json` y `operations.log` junto al binario.
3. Si el port que agregas usa un ejecutable `.exe` de Windows, el botón **Jugar** intentará lanzarlo automáticamente mediante `wine`.

> **Tip**: Puedes agregar los 3 ports (Hookshot, Longshot y NX2NAVI) y cambiar entre ellos en 1 clic desde el selector **PORT ACTIVO** en la esquina inferior izquierda.

---

## 2. Barra superior: Perfil global y Jugar

Un **Perfil global** agrupa bajo un mismo nombre tus **partidas** y tu **selección de mods** (siempre que esté marcada la casilla *Vincular mods al perfil global*):

- **Selector de perfil**: elige el perfil que quieres inspeccionar o activar.
- **Activar perfil**: respalda tus partidas activas actuales, carga las del perfil seleccionado en el juego y aplica su lista de mods vinculados.
- **`+ Guardar perfil…`**: guarda las partidas activas actuales y los mods activos en un perfil nuevo (o actualiza uno existente previo respaldo).
- **`Importar save…`**: selecciona una carpeta exportada de emulador (que contenga `slot_00..slot_05`, aunque estén en subcarpetas) o la carpeta de un slot individual (`progress.sav` + `caption.sav`) para crear un perfil global nuevo.
- **Jugar**: prepara/aplica el perfil seleccionado (partidas y mods) y abre el juego.

---

## 3. Secciones de la aplicación

### Partidas
- Muestra las tarjetas de cada slot (`slot_00`..`slot_05`) con su captura real, escena, corazones, rupias, fecha y tamaño.
- El indicador superior te avisa si estás **● VIENDO PERFIL ACTIVO** (lo que cargará el juego) o en **👁 VISTA PREVIA (NO ACTIVO)** (solo estás mirando otro perfil sin aplicarlo todavía).
- En el panel derecho puedes:
  - **Actualizar**: recarga los slots desde disco.
  - **Respaldar slot**: guarda una copia rápida del slot seleccionado en `backups/`.
  - **Exportar…**: copia ese slot a otra carpeta de tu PC.
  - **Importar / restaurar…**: reemplaza el slot seleccionado con una copia externa (respaldando el anterior y sincronizando el perfil activo si estás en la raíz en vivo).

### Inventario y Progreso
- Muestra el detalle real leído de `progress.sav` y `caption.sav` para el slot seleccionado:
  - **Equipamiento**: Espadas, Escudos, Túnicas y Botas.
  - **Piedras Espirituales y Medallones**.
  - **Objetos, Magias, Mejoras y Botellas** (incluyendo el contenido de cada botella).
  - **Estado vital y munición**: Corazones, piezas de corazón, rupias, magia, Skulltulas, munición actual, fecha y coordenadas.

### Mods
- **`Importar ZIP a biblioteca…`**: extrae un mod `.zip` en `Mods/` sin activarlo todavía.
- **`GameBanana URL…`**: pega el enlace de un mod en GameBanana (por ejemplo `https://gamebanana.com/mods/123456`) o su ID numérico para descargarlo e instalarlo directamente en `Mods/`. Si seleccionas un mod descargado de GameBanana y vuelves a pulsar este botón, se pre-rellena su enlace para actualizarlo con respaldo previo.
- **`Activar / desactivar`** *(o doble clic en la fila)*: despliega y activa o desactiva el mod en el port actual.
- **`Desinstalar mod…`**: crea un respaldo y quita el mod de `Mods/` y del port.
- **Ordenar tabla**: haz clic en los encabezados **Mod**, **Tipo** o **Estado**.
- **Conflictos `RomFS`**: si dos mods activos modifican los mismos archivos, aparecerá un aviso amarillo arriba con el botón **Resolver conflictos**.
- **Diferencias entre ports**:
  - **Hookshot** y **Longshot** aplican mods `RomFS` (los mods solo `ExeFS` se marcan como no compatibles).
  - **NX2NAVI** reconoce tanto `RomFS` como `ExeFS`, pero puede marcar algunos `ExeFS` como `Not Usable` según sus registros de ejecución.

### Respaldos
- Muestra todos los respaldos creados automáticamente en `backups/`, permite abrir cualquiera en el explorador de archivos y limpiar respaldos antiguos conservando los **15 más recientes**.

### Configuración
- Permite cambiar manualmente la ruta del port, ver la tabla de ports registrados, elegir la cuenta de guardado (en **NX2NAVI** si hay varias cuentas), activar/desactivar **Vincular mods al perfil global** y cambiar el idioma entre **Español** y **English**.

---

## 4. Recomendaciones importantes

- **Cierra el juego antes de hacer cambios**: antes de cambiar de perfil o activar/desactivar mods, cierra el juego (y el launcher de **NX2NAVI** si está abierto). El gestor bloqueará las escrituras si detecta el proceso abierto para proteger tus partidas.
- **Portabilidad**: si mueves `OcarinaRemakeManager.exe` a otra carpeta, recuerda mover también su carpeta `Mods/`, `backups/` y `settings.json` si quieres conservar tu biblioteca y configuración.
