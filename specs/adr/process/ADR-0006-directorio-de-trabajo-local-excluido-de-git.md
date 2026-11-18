# ADR-0006 · Directorio de trabajo local excluido de git

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

Mientras trabaja, Claude produce ficheros que no son del repo: planes de oleadas y manifiestos de agentes, cuerpos de PR, informes de revisión y de seguridad, notas y temporales. Hasta ahora las skills los mandaban al scratchpad de la sesión. El scratchpad se pierde al cerrarla y no tiene estructura, así que un informe de revisión o un plan no se pueden retomar en la sesión siguiente. Cada persona acaba creando su propio directorio local, con nombres distintos y, a veces, subiéndolo por error.

## Decisión

1. Cada repo adoptado tiene un directorio de trabajo local `.work/` en su raíz, con subdirectorios de serie: `plans/`, `merge-request/`, `security-report/`, `reviews/`, `notes/` y `tmp/`. `work.dirs` añade otros.
2. Se excluye de git con una línea `/.work/` en `.git/info/exclude`, no en `.gitignore`. Así el plugin no modifica ningún fichero versionado del repo destino, y la exclusión vive en cada clon.
3. El hook de sesión lo crea y lo excluye en cada sesión, de forma idempotente. `mth init` lo hace también al adoptar. `mth doctor` lo comprueba.
4. El guard bloquea los `git add` forzados que lo incluirían.
5. Las skills guardan ahí lo que antes iba al scratchpad. El scratchpad queda para antes de adoptar, cuando el plugin no actúa en el repo.

## Alternativas consideradas

- **Línea en `.gitignore`:** queda explícita para todo el equipo, pero modifica un fichero versionado del repo destino y exige una migración en cada repo ya adoptado.
- **Seguir con el scratchpad:** no persiste entre sesiones y no tiene estructura.
- **Directorio fuera del repo (por ejemplo, en `~/.claude`):** no se pierde nada, pero queda lejos del repo, se mezcla entre clones y quien trabaja no lo encuentra.

## Consecuencias

- **Positivas:** los artefactos de trabajo persisten entre sesiones, con la misma estructura en todos los repos y sin tocar ficheros versionados.
- **Negativas:** la exclusión no viaja con el repo: un clon sin sesión de Claude Code no la tiene hasta que se abre una o se ejecuta `mth init`/`mth doctor`.
- **Riesgo aceptado:** un `git add` forzado escrito de forma que el guard no reconozca podría versionarlo. El guard es una barrera de ayuda, no de seguridad.
