# Changelog

Todos los cambios relevantes de este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Los cambios pendientes de publicar viven como fragmentos en `changes/` y se incorporan aquí al publicar cada versión.

<!-- mth:releases -->

## [0.5.0] - 2026-11-18

### Añadido
- Plan de trabajo en la spec (sección `## Plan de trabajo`): tareas por oleadas con sus ficheros permitidos y sus criterios. `mth plan check SPEC-NNNN` lo valida antes de delegar: formato, criterios existentes y asignados, y que dos tareas de la misma oleada no compartan ficheros. `mth trace` aplica las mismas comprobaciones a toda spec que tenga la sección. (SPEC-0001, ADR-0001)
- `mth plan verify SPEC-NNNN --wave N --manifest FICHERO …` verifica una oleada contra los manifiestos JSON de sus agentes: rechaza tareas sin manifiesto (no ejecutadas), bloqueadas o fallidas (no completadas), manifiestos inválidos, criterios sin cubrir, tests ausentes o en rojo, ficheros fuera del alcance de la tarea, cambios que nadie declara y ficheros declarados sin cambios reales. Los desvíos se muestran como avisos. (SPEC-0001, ADR-0001)
- `mth-develop` describe el protocolo de delegación por oleadas: encargo con los ficheros permitidos de la tarea, manifiesto JSON guardado sin editar, verificación al cerrar cada oleada y un único reintento por tarea fallida. (SPEC-0001, ADR-0001)
- Tabla `[models]` en `.claude/methodology.toml`: escalera de reintento (`ladder`, por defecto `haiku`, `sonnet`, `opus`) y nivel de las tareas, de los revisores y del documentador. `mth models` la muestra y una configuración inválida falla antes de ejecutar nada. (SPEC-0002, ADR-0002)
- Columna opcional `Modelo` en el plan de trabajo de la spec: cada tarea declara el modelo que necesita; si la celda está vacía, se usa `models.task`. (SPEC-0002, ADR-0002)
- `mth plan model SPEC-NNNN T-NN [--retry]` imprime el alias que hay que pasar a la herramienta Agent; con `--retry`, el siguiente nivel de la escalera, de modo que un reintento no repite el modelo que falló. (SPEC-0002, ADR-0002)
- `mth plan verify --model T-NN=alias` indica con qué modelo se ejecutó cada tarea y registra un evento `plan.task` por tarea (modelo, resultado y huella del manifiesto) en `.git/mth/trace.jsonl`. (SPEC-0002, ADR-0002)
- `mth plan stats [--spec SPEC-NNNN]` resume por modelo los intentos, los aciertos y el porcentaje de `ok`, para ajustar los niveles con evidencia. (SPEC-0002, ADR-0002)
- Las skills usan esos niveles: `mth-develop` elige el modelo de cada tarea delegada, escala en el reintento y lanza el documentador con `models.documenter`; `mth-review` lanza los revisores con `models.review`. (SPEC-0002, ADR-0002)

### Cambiado
- `mth review record` exige `--report INFORME` y toma el número de bloqueantes de la última línea del informe del revisor (`BLOQUEANTES: N`). Un informe ausente, vacío, de más de 256 KiB o sin esa línea no se registra y la revisión sigue pendiente. `--blocking` desaparece: actualiza los scripts o hábitos que lo usen. (SPEC-0001, ADR-0001)
- `mth plan check` muestra el modelo efectivo de cada tarea, por ejemplo `Oleada 1: T-01 (haiku), T-02 (sonnet)`. (SPEC-0002, ADR-0002)

## [0.4.0] - 2026-11-18

### Añadido
- SOLID como práctica de diseño obligatoria en clases, módulos y componentes (apartado 2 de `PRINCIPLES.md`), aplicada con proporcionalidad: los puntos de extensión solo se crean con variantes reales.
- Principios contra los antipatrones STUPID: dependencias explícitas sin estado global oculto, bajo acoplamiento, testable por diseño y optimización con evidencia (apartado 2 de `PRINCIPLES.md`); nombres que revelan intención y sin duplicación de conocimiento (apartado 5). Las reglas base de sesión los resumen.

## [0.3.1] - 2026-11-10

### Añadido
- Protocolo de orquestación en `mth-develop`: la sesión principal divide la spec en tareas con ficheros disjuntos, delega en los agentes `dev-*` del repo con un encargo autocontenido y recibe un manifiesto; los commits los hace siempre la sesión principal.

## [0.3.0] - 2026-11-10

### Añadido
- Agentes compartidos en el plugin: `verificador` (cumplimiento real de la spec, tests válidos, regresión y afirmaciones falsas) y `documentador` (docs, fragmento y registros documentales del repo).
- Revisores condicionales por rutas (`[review.paths]`, globs con negación `!`): solo se exigen si el diff toca su área. `mth review status` muestra los obligatorios de la rama.
- `mth doctor` reconoce los agentes del plugin además de los del repo.

### Cambiado
- Todas las llamadas a `gh` indican el repositorio de `origin` (`--repo`): nunca se elige entre `origin` y `upstream` por defecto.
- La plantilla declara `verificador` como primer revisor y los roles `documenter` y `verifier`.

## [0.2.1] - 2026-11-10

### Corregido
- Los hooks y el hook `commit-msg` usan un lanzador que busca un Python >= 3.11 en lugar de depender de `python3`: con pyenv o un venv en una versión anterior, el guard quedaba desactivado sin avisar y el contexto de sesión no se inyectaba. `MTH_PYTHON` permite fijar el intérprete.

## [0.2.0] - 2026-11-10

### Añadido
- Soporte de forks: `release.tag_prefix`, `commits.external_refs`, `trace.include` y `paths.claude_md`.
- `mth init --config` adopta la metodología con una configuración preparada, validada antes de tocar el repo.
- Ramas de primer nivel `security` con sección y bump propios en el fragmento.

### Cambiado
- Los mensajes de merge listan como máximo 50 commits propios.

## [0.1.0] - 2026-11-10

### Añadido
- Principios de desarrollo con precedencia explícita y mecanismo de imposición por regla.
- CLI determinista `mth`: ramas, commits validados, sync, integración por PR con merge commit, releases y hotfixes reanudables.
- Trazabilidad: IDs definidos y únicos, referencias, enlaces internos y cobertura de criterios de aceptación.
- Changelog por fragmentos agregado en cada versión.
- Hooks de Claude Code: contexto de sesión y guard contra reescritura de historia.
- Skills `mth-*` para todo el ciclo.
