# ADR-0002 · Niveles de modelo en el plan y escalera de reintento

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process
- Formato: compacto

## Contexto

- [SPEC-0002](../../features/SPEC-0002-niveles-de-modelo.md) delega las tareas del plan en modelos más baratos cuando basta con ellos.
- Quien planifica (la sesión principal, normalmente Opus) conoce la dificultad de cada tarea.
- Cada repo tiene su equilibrio coste/calidad; un plugin compartido no debe imponerlo.
- Un reintento con el mismo modelo que ya falló suele volver a fallar.
- Los niveles se ajustan con datos (PRINCIPLES §2).
- Los alias (`haiku`, `sonnet`, `opus`, `fable`) los entiende la herramienta Agent de Claude Code, que los resuelve a la versión vigente.
- Matizado por [ADR-0021](ADR-0021-planes-acordados-antes-de-desarrollar.md): el planificador siempre usa `opus`, fijado por la skill que lo lanza y no por su cabecera ni por la configuración.

## Decisión

1. Los valores por defecto DEBEN ir en la tabla `[models]` del repo: la escalera (`ladder`) y el nivel de tareas, revisores y documentador. El modelo NO DEBE fijarse en el frontmatter de los agentes del plugin.
2. Una tarea PUEDE declarar su nivel en la columna opcional `Modelo` del plan; sin ella toma `models.task`.
3. El reintento DEBE subir un nivel de la escalera; en el último nivel, repite.
4. Solo DEBEN admitirse los alias de la herramienta Agent; un alias nuevo exige actualizar `mth`. Una errata se detecta al cargar la configuración (fail-fast).
5. Las métricas DEBEN salir de eventos `plan.task` de la traza local (`.git/mth/trace.jsonl`), deduplicados por intento con la huella del manifiesto.

## Rechazado

- `model:` en el frontmatter de cada agente: fija un modelo por agente, no por tarea, y obliga a todos los repos a aceptar el del plugin. Los `dev-*` de cada repo pueden seguir usándolo; la columna del plan lo sustituye.
- Escalar directo a Opus en el reintento: desperdicia el paso intermedio cuando Haiku falla y Sonnet bastaría.
- Elegir el modelo según las métricas: con pocas ejecuciones los porcentajes no son fiables y oscilaría. `mth` informa; decide quien planifica.
- Admitir cualquier nombre de modelo: una errata (`sonet`) solo aparecería al lanzar el agente, a mitad de una oleada.
- Base de métricas propia: la traza ya registra cada operación con su ID de ejecución; un fichero nuevo duplicaría la fuente.

## Consecuencias

- **+** Las tareas mecánicas cuestan una fracción; `mth plan verify` detecta el fallo de un modelo barato y el reintento sube de nivel.
- **−** La sesión principal pasa el alias al lanzar cada agente y `--model` al verificar si cambió; sin `--model` en un reintento, la métrica atribuye el intento al nivel planificado.
- **riesgo** Las métricas son locales y de una máquina → orientan, no son estadística rigurosa.

## Impone

- [script] `mthlib/config.py`: `[models]` y alias válidos (`MODEL_ALIASES`) validados al cargar; `mth models` y `mth plan` (modelo de una tarea, métricas).
- [criterio] `revisor-adr`: ningún agente del plugin fija `model` en el frontmatter.
