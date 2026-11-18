---
bump: patch
refs: SPEC-0003
---
### Corregido
- Al publicar, los ficheros de `release.version_files` conservan sus finales de línea: un fichero con CRLF ya no se reescribe entero con LF.
- Un patrón de `release.version_files` cuyo grupo de captura es opcional y no captura nada ya no corrompe el fichero al publicar: `mth release`, `mth hotfix finish` y `mth doctor` lo rechazan sin modificar nada.
