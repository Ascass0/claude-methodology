---
bump: minor
refs: SPEC-0002, ADR-0002
---
### Añadido
- Tabla `[models]` en `.claude/methodology.toml`: escalera de reintento (`ladder`, por defecto `haiku`, `sonnet`, `opus`) y nivel de las tareas, de los revisores y del documentador. `mth models` la muestra y una configuración inválida falla antes de ejecutar nada.
- Columna opcional `Modelo` en el plan de trabajo de la spec: cada tarea declara el modelo que necesita; si la celda está vacía, se usa `models.task`.
- `mth plan model SPEC-NNNN T-NN [--retry]` imprime el alias que hay que pasar a la herramienta Agent; con `--retry`, el siguiente nivel de la escalera, de modo que un reintento no repite el modelo que falló.
- `mth plan verify --model T-NN=alias` indica con qué modelo se ejecutó cada tarea y registra un evento `plan.task` por tarea (modelo, resultado y huella del manifiesto) en `.git/mth/trace.jsonl`.
- `mth plan stats [--spec SPEC-NNNN]` resume por modelo los intentos, los aciertos y el porcentaje de `ok`, para ajustar los niveles con evidencia.
- Las skills usan esos niveles: `mth-develop` elige el modelo de cada tarea delegada, escala en el reintento y lanza el documentador con `models.documenter`; `mth-review` lanza los revisores con `models.review`.

### Cambiado
- `mth plan check` muestra el modelo efectivo de cada tarea, por ejemplo `Oleada 1: T-01 (haiku), T-02 (sonnet)`.
