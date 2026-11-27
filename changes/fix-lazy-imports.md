---
bump: patch
refs: SPEC-0004, SPEC-0012, SPEC-0014, SPEC-0022, SPEC-0023, SPEC-0025, SPEC-0028, ADR-0023
---
### Cambiado
- Cada comando de `mth` importa solo los módulos que usa, en lugar de cargar toda la CLI al arrancar. Medianas de 20 ejecuciones: `mth --version` de 126 a 50 ms, `mth plan list` de 137 a 104 ms, `mth models` de 140 a 105 ms y `mth review status` de 143 a 116 ms; con el lanzador `sh`, `mth status` baja de 173 a 141 ms. La salida, el stderr y el código de salida son idénticos en los 40 casos comparados, incluida la ayuda de cada subcomando.
- La configuración ya no carga el gestor de herramientas ni los módulos de archivos (`tarfile`, `zipfile`, `hashlib`, `platform`) en cada comando: se importan cuando se descarga, se extrae o se calcula un digest.
- El hook de sesión deja de cargar el código de adopción (`setup`, `adoption`, `survey`, `audit`): los hooks de git y el registro del lanzador viven ahora en `mthlib/hooks.py`.
- Sin mejora apreciable: el hook de sesión (~125 ms) y `mth trace` (~270 ms), que dependen sobre todo de validar la configuración y de leer los documentos.
