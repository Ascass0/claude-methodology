---
bump: minor
refs: SPEC-0003
---
### Añadido
- Nueva lista `release.version_files` en `.claude/methodology.toml` para declarar los ficheros que contienen la versión del proyecto (`package.json`, `pyproject.toml`, `plugin.json`…). Cada entrada tiene `path` (ruta relativa al repo) y `pattern` (expresión regular con exactamente un grupo de captura: la versión). Por defecto está vacía. Una entrada inválida (claves que faltan o sobran, ruta absoluta o con `..`, regex inválida o sin exactamente un grupo, entrada duplicada) hace fallar la carga de la configuración y ningún comando `mth` se ejecuta hasta corregirla.
- `mth release` y `mth hotfix finish` comprueban estos ficheros antes de crear la rama o el commit de la versión: deben existir y el patrón debe aparecer exactamente una vez; si no, no publican ni modifican nada. Después sustituyen la versión en el mismo commit `chore(release)` que el CHANGELOG y listan los ficheros actualizados en su cuerpo.
- `mth doctor` muestra la versión que declara cada fichero: ✓ si coincide con la última etiqueta, ⚠ si está desfasada y ✗ si el fichero no existe o el patrón no aparece exactamente una vez.
- La plantilla de `methodology.toml` incluye un ejemplo de `release.version_files`.

