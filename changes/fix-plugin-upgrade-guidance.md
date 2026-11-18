---
bump: patch
refs: SPEC-0009
---
### Corregido
- El error de clave desconocida en `.claude/methodology.toml` indica la versión del plugin que la rechaza y explica que, si no es una errata, hay que actualizar el plugin con `/plugin` y abrir una sesión nueva. `mth doctor` muestra ahora también la pista de los errores de configuración.

### Cambiado
- Las claves que añade esta versión (`language`, `hooks`, `autonomy`, `trace.legacy_base` y `release.version_files`) bloquean a quien siga con la 0.5.x: ningún comando `mth` se ejecuta y su hook `commit-msg` rechaza los commits. Actualiza el plugin en todo el equipo antes de añadirlas; el README explica el orden en "Actualizar el plugin".
