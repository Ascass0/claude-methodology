---
bump: patch
refs: SPEC-0013, ADR-0009
---
### Corregido
- `mth review record` ya no se fía del número que declara el revisor: cuenta él mismo los hallazgos `[bloqueante]` de `HALLAZGOS` y contrasta la línea `BLOQUEANTES: <n>`. Una discrepancia o un informe ilegible (sección ausente, viñetas, texto suelto, severidad desconocida, vacío, ausente o de más de 256 KiB) se registra como revisión **fallida**: no aprueba nada, `mth review status` muestra el motivo y `mth integrate` la rechaza. (SPEC-0013)
- El informe de cada intento se archiva byte a byte en `.work/reviews/<sha>-<agente>-<n>.md` sin sobrescribir nunca, y el registro guarda su `sha256` y el número de intentos por agente y commit, para ver si el fallo está en el prompt del revisor. Ante un fallo, la skill `mth-review` pide una única corrección al mismo agente con `SendMessage`. (SPEC-0013, ADR-0009)
