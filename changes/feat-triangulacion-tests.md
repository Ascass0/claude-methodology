---
bump: minor
refs: SPEC-0019, ADR-0015
---
### Añadido
- Cada test declara por qué existe con una etiqueta en su comentario: `verifies: SPEC-NNNN/AC-NN` (o `/FM-NN`), `regression:` con una referencia o `unit:` con un símbolo público. `mth trace` reporta como error un test sin etiqueta y `mth integrate` se detiene; en ficheros legados (`trace.legacy_base`) es solo un aviso.
- `trace.test_patterns` (glob → regex de la línea que abre un test) con valores por defecto para Python, JS/TS y Go; en otro lenguaje se exige al menos una etiqueta por fichero de tests.
- `mth trace` avisa de los criterios con un único test (`mth trace --single` los lista), sin cambiar el código de salida.
- Triangulación en PRINCIPLES §6 (dos ejemplos de clases distintas por AC con entrada variable), ciclo en `mth-develop`, criterios nuevos en `revisor-parsimonia` (tests de la misma clase) y `revisor-fallos` (casos especiales para los valores del test, bloqueante), con sus evals. Ambos revisores pasan a 1.1.0.

### Cambiado
- **Cambio incompatible (`BREAKING CHANGE`).** Un repo adoptado con tests sin etiquetar verá errores en `mth trace` y `mth integrate` bloqueado. Para migrar, elige una de las dos:
  1. Etiqueta los tests: añade en cada uno un comentario `# verifies: SPEC-NNNN/AC-NN` (o `/FM-NN`), `# regression:` con el issue o `# unit:` con la función. `mth trace` lista fichero y línea.
  2. Declara lo anterior como heredado: pon en `trace.legacy_base` el commit actual de `development`. Sus tests sin etiqueta quedan como avisos (`mth trace --legacy`) hasta que alguien los toque; los tests nuevos sí deben llevar etiqueta.

  Si tu lenguaje no es Python, JS/TS ni Go, añade su patrón en `[trace.test_patterns]`; sin él, basta una etiqueta por fichero de tests.
