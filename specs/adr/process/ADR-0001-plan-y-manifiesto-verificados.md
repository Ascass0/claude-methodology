# ADR-0001 · Plan de trabajo en la spec y manifiesto JSON verificado por mth

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process
- Formato: compacto

## Contexto

- La delegación en agentes `dev-*` ([SPEC-0001](../../features/SPEC-0001-delegacion-verificable.md)) necesita dos formatos que `mth` lea de forma determinista: el reparto de tareas (ficheros y oleada) y lo que devuelve cada agente.
- Una sola fuente de verdad: el reparto deriva de los criterios de la spec y cambia con ella.
- Legibilidad: personas y revisores sin contexto leen specs y planes.
- Sin dependencias: `mth` solo usa la biblioteca estándar de Python ≥ 3.11.
- Fail-safe: ante una duda (formato ambiguo, glob que podría solaparse) se rechaza.
- Matizado por [ADR-0021](ADR-0021-planes-acordados-antes-de-desarrollar.md): existe además un plan acordado local anterior a la spec; este ADR rige solo el «Plan de trabajo» de una spec.

## Decisión

1. El plan de trabajo DEBE ser la sección `## Plan de trabajo` de la propia spec, con tabla de columnas fijas (`Tarea | Oleada | Ficheros | Criterios`). `mth plan check` y `mth trace` la validan.
2. El manifiesto de cada tarea DEBE ser un objeto JSON con campos fijos y sin campos adicionales, validado por código propio de `mth` (sin JSON Schema).
3. Al cerrar cada oleada, antes de confirmarla, `mth` DEBE comparar los manifiestos con el plan y con los cambios reales del árbol respecto a HEAD.
4. El resultado de un revisor DEBE salir de su informe, no de un número que escriba la sesión principal. La forma concreta (última línea `BLOQUEANTES: <n>`) la sustituye [ADR-0009](ADR-0009-el-numero-de-bloqueantes-lo-calcula-mth.md): lo calcula `mth`.

## Rechazado

- Plan en fichero aparte (TOML o YAML): separa el reparto de los criterios que reparte y duplica IDs.
- Bloque TOML dentro de la spec: peor de leer; la tabla con columnas fijas y validación estricta es igual de determinista.
- JSON Schema: exige la dependencia `jsonschema` o un subconjunto propio; una validación explícita es más simple y da mejores mensajes.
- Manifiesto en prosa: no se verifica y deja pasar agentes caídos o incompletos.
- Ramas hijas o worktrees por tarea: aíslan mejor, pero exigen un PR por tarea, excesivo para tareas de minutos. Abierto para una spec futura.

## Consecuencias

- **+** Se comprueba el alcance de cada agente, se detectan solapamientos antes de delegar y un agente caído no pasa por terminado.
- **−** Las tareas de una oleada comparten árbol: un agente puede ver ficheros a medio escribir; los errores se detectan al cerrar la oleada.
- **−** La comprobación de solapamiento entre globs es conservadora y puede rechazar planes válidos → se resuelve listando rutas exactas.
- **riesgo** La sesión principal podría editar un manifiesto para que pase → la skill lo prohíbe y el manifiesto se archiva fuera del repo, sin impedimento técnico.

## Impone

- [script] `mthlib/plan.py`: validación del plan y verificación de la oleada (`mth plan check`, `mth plan verify`); `mth trace` valida el plan en la spec.
- [criterio] `verificador`: el manifiesto no se edita para que pase.
