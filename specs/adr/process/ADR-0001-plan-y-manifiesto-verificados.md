# ADR-0001 · Plan de trabajo en la spec y manifiesto JSON verificado por mth

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

La delegación en agentes `dev-*` ([SPEC-0001](../../features/SPEC-0001-delegacion-verificable.md)) necesita dos formatos que `mth` pueda leer de forma determinista: el reparto de tareas (qué ficheros puede tocar cada una y en qué oleada) y lo que devuelve cada agente. Fuerzas en juego:

- **Una sola fuente de verdad:** el reparto deriva de los criterios de la spec y cambia con ella.
- **Legibilidad:** specs y planes los leen personas y revisores sin contexto.
- **Sin dependencias:** `mth` solo usa la biblioteca estándar de Python ≥ 3.11.
- **Fail-safe:** ante una duda (formato ambiguo, glob que podría solaparse) se rechaza.

## Decisión

1. El plan de trabajo es una sección `## Plan de trabajo` de la propia spec, con una tabla markdown de columnas fijas (`Tarea | Oleada | Ficheros | Criterios`). `mth` la valida en `mth plan check` y en `mth trace`.
2. El manifiesto de cada tarea es un objeto JSON con campos fijos y sin campos adicionales, validado por código propio de `mth` (sin JSON Schema).
3. La verificación compara los manifiestos con el plan y con los cambios reales del árbol de trabajo respecto a HEAD, al cerrar cada oleada, antes de confirmarla.
4. El resultado de un revisor se toma de la última línea de su informe (`BLOQUEANTES: <n>`), no de un número que escribe la sesión principal.

## Alternativas consideradas

- **Plan en un fichero aparte (TOML o YAML):** más fácil de procesar, pero separa el reparto de los criterios que reparte y duplica IDs en dos sitios. Se descarta por la fuente única de verdad.
- **Bloque TOML dentro de la spec:** robusto de procesar, pero peor de leer para revisores y personas. La tabla, con columnas fijas y validación estricta, es igual de determinista.
- **Validar con JSON Schema:** exige una dependencia (`jsonschema`) o un subconjunto propio de todos modos. El manifiesto es pequeño y estable: una validación explícita es más simple y da mejores mensajes de error.
- **Manifiesto en prosa (como hasta ahora):** no se puede verificar y deja pasar agentes caídos o incompletos.
- **Ramas hijas o worktrees por tarea:** aíslan mejor, pero una rama hija exige una integración con PR por tarea, demasiado para tareas de minutos. Queda abierto para una spec futura.

## Consecuencias

- **Positivas:** el alcance de cada agente se comprueba, los solapamientos se detectan antes de delegar, un agente caído no pasa por terminado y el número de bloqueantes de una revisión deja de depender de quien la registra.
- **Negativas:** las tareas de una oleada comparten árbol de trabajo, así que un agente puede ver ficheros a medio escribir por otro; los errores se detectan al cerrar la oleada, no al escribir. La comprobación de solapamiento entre globs es conservadora y puede rechazar planes que en realidad no se solapan: se resuelve listando rutas exactas.
- **Riesgo aceptado:** la sesión principal podría editar un manifiesto para que pase. La skill lo prohíbe y el manifiesto se archiva fuera del repo, pero no se impide técnicamente.
