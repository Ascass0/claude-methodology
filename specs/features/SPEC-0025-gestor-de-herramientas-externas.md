# SPEC-0025 · Gestor de herramientas externas

- Estado: borrador
- Fecha: 2026-11-27
- Formato: compacto
- ADRs: [ADR-0023](../adr/security/ADR-0023-gestor-de-herramientas-externas.md)
- Sustituye a: —

## Contexto

- Los gates de `mth` dependen de herramientas externas (`gitleaks` hoy; más con el auditor de hardening). Hasta ahora `mth` solo las busca en el `PATH` y cada persona las instala a mano.
- [ADR-0023](../adr/security/ADR-0023-gestor-de-herramientas-externas.md) fija un gestor que las descarga bajo demanda y de forma explícita, verifica lo descargado y las deja en una caché del usuario, sin empaquetar binarios ni activar nada en silencio ([ADR-0020](../adr/security/ADR-0020-gate-de-secretos-en-el-historial.md)).

## Objetivo

1. Una herramienta del `PATH` sigue mandando; si no hay, `mth` usa su copia gestionada.
2. La persona instala una herramienta con una orden explícita y lo descargado se verifica antes de ejecutarse.
3. Añadir una herramienta es añadir una entrada de datos al manifiesto, sin código nuevo.

## Fuera de alcance

- Empaquetar binarios en el plugin y descargar sin orden explícita.
- Ofrecer la instalación en `mth-init` o `mth update`, y guardar consentimientos en la configuración.
- Paquetes Python (Checkov, ssh-audit) y ejecutables sueltos sin archivo.
- Verificar firmas (cosign) y herramientas distintas de `gitleaks` en el manifiesto: sus entradas llegan con el plan que las necesite.
- Cambiar qué escanea el gate de secretos o la plantilla de CI.

## Comportamiento

### Manifiesto

- Fichero `plugins/methodology/tools/manifest.toml`: una tabla por herramienta con `version`, `version_args` (argumentos que imprimen su versión) y una subtabla `platforms.<sistema>_<arquitectura>`.
- Cada plataforma declara `url` (https), `sha256` (64 hexadecimales), `format` (`tar.gz` o `zip`) y `entry` (ruta relativa del ejecutable dentro del archivo, que puede formar parte de un árbol de ficheros).
- Sistemas: `linux`, `darwin`, `windows`. Arquitecturas: `x64`, `arm64`. `gitleaks` 8.30.1 lleva `linux_x64`, `linux_arm64`, `darwin_x64`, `darwin_arm64` y `windows_x64`.
- Se valida al cargarlo: un campo ausente o inválido da un error que nombra herramienta, plataforma y campo.

### Resolución

1. Si la herramienta está en el `PATH` (sin shell) y su versión alcanza la mínima que pide quien la usa, se usa esa (`origen: PATH`).
2. Si la del `PATH` es anterior a la mínima o su versión no se reconoce, y hay copia gestionada válida, se usa la gestionada; sin copia gestionada se usa la del `PATH` y se avisa.
3. Sin `PATH`, se usa la copia gestionada (`origen: gestionada`) tras comprobar su integridad.
4. Sin ninguna, error con la orden `mth tools install <herramienta>`. Resolver nunca descarga.

### Caché

- `<caché>/claude-methodology/tools/<herramienta>/<versión>/`, con `<caché>` = `$MTH_TOOLS_DIR` si existe; si no, `$XDG_CACHE_HOME` o `~/.cache` (Linux), `~/Library/Caches` (macOS) o `%LOCALAPPDATA%` (Windows). Los directorios se crean con permisos solo del usuario.
- `.installed.json` guarda la suma del archivo y la del ejecutable al instalar.

### `mth tools`

| Forma | Hace |
|---|---|
| `mth tools` | Lista cada herramienta del manifiesto con su versión, su origen (`PATH`, `gestionada` o `ausente`) y la versión encontrada; no usa la red |
| `mth tools install <herramienta> [--force]` | Descarga, verifica, extrae y publica la copia gestionada de la versión del manifiesto; con `--force` la reinstala |
| `mth tools prune` | Borra las versiones gestionadas que ya no están en el manifiesto y las instalaciones a medias |

### Instalación

- Descarga con tiempo máximo por intento, tamaño máximo y reintentos acotados con espera creciente. Respeta las variables de proxy del sistema.
- La suma SHA-256 del archivo se comprueba antes de extraer nada; una suma distinta aborta sin dejar nada instalado.
- Extrae solo ficheros y directorios, con tamaño total y número de miembros acotados; rechaza rutas absolutas, `..`, enlaces simbólicos o duros y ficheros especiales.
- Instala en un directorio temporal de la misma caché y lo publica con un renombrado atómico. Si la versión ya está instalada y es válida, no descarga.

### Consumidores

- `secretgate` ejecuta la ruta resuelta de `gitleaks` (mínima 8.19.0) y, sin herramienta, falla cerrado con un remedio que cita `mth tools install gitleaks`.
- `mth doctor` informa del origen y la versión: ✓ con origen `PATH` o `gestionada`; ⚠ si la copia gestionada es de otra versión que la del manifiesto o si la del `PATH` es anterior a la mínima; ✗ como hasta ahora si un gate activo no encuentra la herramienta.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Manifiesto con un campo ausente o inválido | Error que nombra herramienta, plataforma y campo; nada se instala | AC-01 |
| FM-02 | La plataforma no tiene entrada en el manifiesto | Error que nombra la plataforma y las admitidas; nada se instala | AC-02 |
| FM-03 | La suma del archivo no coincide | Error; no se extrae ni se instala nada y se borra lo descargado | AC-06 |
| FM-04 | La descarga falla, se corta, es lenta o supera el tamaño máximo | Reintentos acotados y error que indica la URL y cómo instalar a mano en el `PATH`; nada se instala | AC-06 |
| FM-05 | El archivo trae rutas fuera del destino, enlaces, ficheros especiales o supera los límites; o falta el ejecutable `entry` | Error; nada se instala | AC-07 |
| FM-06 | La caché no se puede crear o escribir | Error que nombra la ruta y `MTH_TOOLS_DIR`; nada se instala | AC-09 |
| FM-07 | Dos instalaciones simultáneas de la misma versión | Queda una sola copia válida; la segunda reutiliza la primera | AC-08 |
| FM-08 | La copia gestionada se alteró tras instalarla | Error cerrado que pide `mth tools install <herramienta> --force`; no se ejecuta | AC-10 |
| FM-09 | La herramienta del `PATH` es anterior a la mínima o su versión no se reconoce | Se prefiere la gestionada si es válida; si no, se usa la del `PATH` con aviso | AC-04 |
| FM-10 | El comando de versión falla o no termina | Cuenta como versión no reconocida (tiempo máximo de 30 s) | AC-04 |

## Criterios de aceptación

- **AC-01**: SI el manifiesto tiene un campo ausente o inválido (`version`, `version_args`, `url` no https, `sha256` que no son 64 hexadecimales, `format` desconocido, `entry` vacía o con `..`), ENTONCES `mth` DEBE fallar nombrando herramienta, plataforma y campo.
- **AC-02**: CUANDO se necesita una plataforma sin entrada, `mth tools install` DEBE fallar nombrando la plataforma y las admitidas; la plataforma se deduce del sistema y la arquitectura de la máquina.
- **AC-03**: SI la herramienta está en el `PATH` y su versión alcanza la mínima, ENTONCES el resolvedor DEBE devolver esa, sin shell y sin usar la red.
- **AC-04**: SI la herramienta del `PATH` es anterior a la mínima o su versión no se reconoce, ENTONCES el resolvedor DEBE preferir la copia gestionada válida y, sin ella, devolver la del `PATH` marcada para avisar; un comando de versión que falla o no termina en 30 s DEBE contar como versión no reconocida.
- **AC-05**: SI la herramienta no está en el `PATH` ni hay copia gestionada, ENTONCES el resolvedor DEBE fallar con la orden `mth tools install <herramienta>` y NO DEBE descargar nada.
- **AC-06**: CUANDO se ejecuta `mth tools install`, `mth` DEBE descargar con tiempo máximo, tamaño máximo y reintentos acotados y comprobar el SHA-256 del archivo antes de extraer; SI la suma no coincide o la descarga falla, ENTONCES DEBE fallar sin dejar nada instalado ni restos temporales.
- **AC-07**: SI el archivo contiene rutas absolutas o con `..`, enlaces, ficheros especiales o supera los límites de tamaño o de miembros, o no contiene `entry`, ENTONCES `mth tools install` DEBE fallar sin dejar nada instalado.
- **AC-08**: CUANDO la versión ya está instalada y es válida, `mth tools install` NO DEBE descargar; con instalaciones simultáneas DEBE quedar una sola copia válida y nunca una a medias.
- **AC-09**: La caché DEBE ubicarse según `MTH_TOOLS_DIR` o el directorio de caché del sistema, con permisos solo del usuario; SI no se puede crear o escribir, ENTONCES `mth` DEBE fallar nombrando la ruta.
- **AC-10**: ANTES de resolver una copia gestionada, `mth` DEBE comprobar que su ejecutable coincide con la suma guardada al instalar; SI no coincide, ENTONCES DEBE fallar sin ejecutarla.
- **AC-11**: `mth tools` DEBE listar cada herramienta con su versión del manifiesto, su origen (`PATH`, `gestionada`, `ausente`) y la versión encontrada, sin usar la red.
- **AC-12**: CUANDO se ejecuta `mth tools prune`, `mth` DEBE borrar solo las versiones gestionadas que ya no están en el manifiesto y las instalaciones a medias, y NO DEBE borrar nada sin esa orden.
- **AC-13**: `secretgate` DEBE ejecutar la ruta resuelta de `gitleaks`; SI no hay herramienta, ENTONCES DEBE fallar cerrado con un remedio que cite `mth tools install gitleaks`, y el resto de su comportamiento NO DEBE cambiar.
- **AC-14**: `mth doctor` DEBE informar del origen y la versión de la herramienta: ✓ con origen `PATH` o `gestionada`, ⚠ si la copia gestionada es de otra versión que la del manifiesto o la del `PATH` es anterior a la mínima, y ✗ si un gate activo no la encuentra.
- **AC-15**: La versión y la suma de `linux_x64` de `gitleaks` en el manifiesto DEBEN coincidir con las de la plantilla de workflow de CI.
- **AC-16**: El README DEBE documentar `mth tools`, el orden de resolución, la caché, la verificación y cómo se añade o actualiza una herramienta del manifiesto.

## Notas

- Tests sin red ni binarios reales: un descargador inyectable sirve archivos generados en el test y una herramienta falsa hace de `gitleaks`.
- La suma del manifiesto se copia de la release oficial de la herramienta y se revisa en el PR; comparte origen con el binario, así que protege de descargas dañadas o alteradas en tránsito, no de una release comprometida (sin firmas, [ADR-0023](../adr/security/ADR-0023-gestor-de-herramientas-externas.md)).
- Con una herramienta en el `PATH` de versión válida distinta de la del manifiesto, gana el `PATH`: manda quien la instaló.
- Sin clave nueva en `methodology.toml`: la instalación es solo por orden explícita y no hay brecha nueva en `mth update`.
- Windows y `.zip` no se pueden probar aquí con binarios reales: se cubren con archivos generados en los tests.
