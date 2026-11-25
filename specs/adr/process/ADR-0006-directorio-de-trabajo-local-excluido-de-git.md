# ADR-0006 · Directorio de trabajo local excluido de git

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process
- Formato: compacto

## Contexto

- Claude produce ficheros que no son del repo: planes de oleadas, manifiestos, cuerpos de PR, informes de revisión y de seguridad, notas y temporales.
- Las skills los mandaban al scratchpad de la sesión: se pierde al cerrarla y no tiene estructura, así que nada se retoma en la sesión siguiente.
- Cada persona acaba creando su propio directorio local, con nombres distintos y a veces subiéndolo por error.

## Decisión

1. Cada repo adoptado DEBE tener `.work/` en su raíz, con `plans/`, `merge-request/`, `security-report/`, `reviews/`, `notes/` y `tmp/`; `work.dirs` añade otros.
2. DEBE excluirse de git con la línea `/.work/` en `.git/info/exclude`, NO en `.gitignore`: el plugin no modifica ningún fichero versionado del destino y la exclusión vive en cada clon.
3. El hook de sesión DEBE crearlo y excluirlo en cada sesión, de forma idempotente; `mth init` también al adoptar; `mth doctor` lo comprueba.
4. El guard DEBE bloquear los `git add` forzados que lo incluirían.
5. Las skills DEBEN guardar ahí lo que antes iba al scratchpad, que queda para antes de adoptar.

## Rechazado

- Línea en `.gitignore`: modifica un fichero versionado del destino y exige migrar cada repo adoptado.
- Seguir con el scratchpad: no persiste entre sesiones ni tiene estructura.
- Directorio fuera del repo (`~/.claude`): queda lejos, se mezcla entre clones y no se encuentra.

## Consecuencias

- **+** Los artefactos persisten entre sesiones, con la misma estructura en todos los repos y sin tocar ficheros versionados.
- **−** La exclusión no viaja con el repo: un clon sin sesión de Claude Code no la tiene hasta abrir una o ejecutar `mth init`/`mth doctor`.
- **riesgo** Un `git add` forzado escrito de forma que el guard no reconozca podría versionarlo → el guard es ayuda, no frontera de seguridad.

## Impone

- [script] `mthlib/work.py` (directorio y exclusión), `mthlib/session.py` (hook de sesión), `mthlib/guard.py` (bloqueo de `git add` forzado).
- [criterio] `mth doctor`: comprueba el directorio de trabajo.
