# ADR-0002 · Niveles de modelo en el plan y escalera de reintento

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

[SPEC-0002](../../features/SPEC-0002-niveles-de-modelo.md) delega las tareas del plan en modelos más baratos cuando basta con ellos. Hay que decidir dónde se fija el modelo de cada tarea, cómo se escala tras un fallo y de dónde salen los datos para ajustarlo. Fuerzas en juego:

- **Quien planifica conoce la dificultad.** La sesión principal (normalmente Opus) escribe el plan y sabe qué tarea es mecánica y cuál pide criterio.
- **Cada repo tiene su equilibrio** entre coste y calidad, y un plugin compartido no debe imponerlo.
- **Coste por tarea terminada:** un reintento con el mismo modelo que ya falló suele volver a fallar.
- **Optimización con evidencia** (PRINCIPLES §2): los niveles se ajustan con datos.
- **Acoplamiento:** los alias los entiende la herramienta Agent de Claude Code (`haiku`, `sonnet`, `opus`, `fable`), que resuelve cada alias a la versión vigente.

## Decisión

1. Los valores por defecto van en una tabla `[models]` del repo: la escalera (`ladder`) y el nivel de las tareas, los revisores y el documentador. El modelo no se fija en el frontmatter de los agentes del plugin.
2. Cada tarea puede declarar su nivel en una columna opcional `Modelo` del plan. Sin ella, toma `models.task`.
3. El reintento sube un nivel en la escalera. En el último nivel, repite.
4. Solo se admiten los alias de la herramienta Agent (`haiku`, `sonnet`, `opus`, `fable`). Un alias nuevo exige actualizar `mth`. A cambio, una errata se detecta al cargar la configuración (fail-fast) y no al lanzar un agente.
5. Las métricas salen de eventos `plan.task` en la traza local existente (`.git/mth/trace.jsonl`). Se deduplican por intento con la huella del manifiesto.

## Alternativas consideradas

- **`model:` en el frontmatter de cada agente:** fija un modelo por agente, no por tarea, y obliga a todos los repos a aceptar el del plugin. Se descarta para los agentes compartidos; los agentes `dev-*` de cada repo pueden seguir usándolo y la columna del plan lo sustituye tarea a tarea.
- **Escalar directamente a Opus en el reintento:** más simple, pero desperdicia el paso intermedio cuando Haiku falla y Sonnet bastaría.
- **Elegir el modelo automáticamente según las métricas:** con pocas ejecuciones, los porcentajes no son fiables y el sistema oscilaría. `mth` informa y decide quien planifica.
- **Admitir cualquier nombre de modelo:** desacopla `mth` de Claude Code, pero una errata (`sonet`) solo aparecería al lanzar el agente, a mitad de una oleada.
- **Una base de métricas propia:** la traza ya registra cada operación con su ID de ejecución. Un fichero nuevo duplicaría la fuente.

## Consecuencias

- **Positivas:** las tareas mecánicas cuestan una fracción. Un fallo de un modelo barato lo detecta `mth plan verify` y el reintento sube de nivel. Los niveles se ajustan con datos de cada repo.
- **Negativas:** la sesión principal tiene que pasar el alias al lanzar cada agente y `--model` al verificar si cambió. Si no indica `--model` en un reintento, la métrica atribuye el intento al nivel planificado.
- **Riesgo aceptado:** las métricas son locales y de una sola máquina. Sirven para orientar, no como estadística rigurosa.
