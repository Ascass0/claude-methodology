# Changelog

Todos los cambios relevantes de este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Los cambios pendientes de publicar viven como fragmentos en `changes/` y se incorporan aquí al publicar cada versión.

<!-- mth:releases -->

## [0.7.0] - 2026-11-18

### Añadido
- Skill `mth-reconfigure`: en un repo ya adoptado, vuelve a pasar la entrevista de la adopción. Se puede rehacer el formulario completo, revisar bloques (`flujo`, `documentacion`, `calidad`, `agente`) o cambiar solo una decisión. (SPEC-0011, ADR-0007)
- `mth survey --reconfigure [--only …]`: inventario de un repo adoptado con cada pregunta aplicable y su valor actual. (SPEC-0011, ADR-0007)
- `mth reconfigure --answers FICHERO [--only …]`: valida las respuestas y las aplica sobre la configuración actual, conservando lo que no se pregunta. Abre `chore/reconfigure-methodology` con la configuración nueva y un ADR de reestructuración que lista cada clave que cambia. Si las respuestas no cambian nada, o no se pueden aplicar, no crea nada. (SPEC-0011, ADR-0007)
- Con `autonomy.level = "supervised"`, el guard pide confirmación para `mth reconfigure`. (SPEC-0011, ADR-0007)
- Directorio de trabajo local `.work/` en cada repo adoptado, con `plans/`, `merge-request/`, `security-report/`, `reviews/`, `notes/` y `tmp/`: ahí deja Claude planes, manifiestos, cuerpos de PR, informes y notas, en lugar del scratchpad de la sesión. El hook de sesión y `mth init` lo crean y lo excluyen de git en `.git/info/exclude`, sin modificar ningún fichero versionado. `mth doctor` lo comprueba y el guard bloquea los `git add` forzados que lo incluirían. (SPEC-0010, ADR-0006)
- `work.dirs` en `.claude/methodology.toml` añade subdirectorios propios del repo a `.work/`. (SPEC-0010, ADR-0006)

### Cambiado
- `mth-review` guarda los informes de los revisores en `.work/reviews/`, `mth-develop` los manifiestos de los agentes en `.work/plans/` y `mth-integrate` propone `.work/merge-request/` para los resúmenes largos de PR. (SPEC-0010, ADR-0006)

## [0.6.0] - 2026-11-18

### Añadido
- Adopción guiada: `mth survey` inventaria el repo sin modificarlo, la skill `mth-init` conduce una entrevista con Opus que solo pregunta lo necesario, y `mth init --answers FICHERO` convierte las respuestas en configuración y en el ADR de adopción. `mth init --decline` desactiva el plugin en ese repo (`.claude/settings.local.json`, no versionado). (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `trace.legacy_base` y `mth trace --legacy`: en una adopción gradual, los hallazgos en ficheros sin cambios desde el commit base son avisos; lo que se toca después cumple todas las reglas. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `hooks.commit_msg` con los valores `own`, `replace` y `chain`: decide qué hacer con un hook `commit-msg` ajeno al instalar el de `mth`. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `autonomy.level` con los valores `full`, `until-pr` y `supervised`: el guard pide confirmación para integrar y publicar, o también para ramas, commits y push. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `language.docs` con los valores `es` y `en`: idioma de docs, specs, ADR, changelog y PR, con plantillas en inglés. Código y commits siguen en inglés. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- Nueva lista `release.version_files` en `.claude/methodology.toml` para declarar los ficheros que contienen la versión del proyecto (`package.json`, `pyproject.toml`, `plugin.json`…). Cada entrada tiene `path` (ruta relativa al repo) y `pattern` (expresión regular con exactamente un grupo de captura: la versión). Por defecto está vacía. Una entrada inválida (claves que faltan o sobran, ruta absoluta o con `..`, regex inválida o sin exactamente un grupo, entrada duplicada) hace fallar la carga de la configuración y ningún comando `mth` se ejecuta hasta corregirla. (SPEC-0003)
- `mth release` y `mth hotfix finish` comprueban estos ficheros antes de crear la rama o el commit de la versión: deben existir y el patrón debe aparecer exactamente una vez; si no, no publican ni modifican nada. Después sustituyen la versión en el mismo commit `chore(release)` que el CHANGELOG y listan los ficheros actualizados en su cuerpo. (SPEC-0003)
- `mth doctor` muestra la versión que declara cada fichero: ✓ si coincide con la última etiqueta, ⚠ si está desfasada y ✗ si el fichero no existe o el patrón no aparece exactamente una vez. (SPEC-0003)
- La plantilla de `methodology.toml` incluye un ejemplo de `release.version_files`. (SPEC-0003)

### Cambiado
- En un repo sin `.claude/methodology.toml`, el plugin ya no inyecta las reglas base ni bloquea comandos: el hook de sesión solo da el aviso de adopción y el guard no actúa hasta que se adopta. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `PRINCIPLES.md` §5 (idioma del código, independiente del de la documentación), §7 (idioma de `language.docs`) y §11 (autonomía según `autonomy.level`). (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- Las claves que añade esta versión (`language`, `hooks`, `autonomy`, `trace.legacy_base` y `release.version_files`) bloquean a quien siga con la 0.5.x: ningún comando `mth` se ejecuta y su hook `commit-msg` rechaza los commits. Actualiza el plugin en todo el equipo antes de añadirlas; el README explica el orden en "Actualizar el plugin". (SPEC-0009)

### Corregido
- El error de clave desconocida en `.claude/methodology.toml` indica la versión del plugin que la rechaza y explica que, si no es una errata, hay que actualizar el plugin con `/plugin` y abrir una sesión nueva. `mth doctor` muestra ahora también la pista de los errores de configuración. (SPEC-0009)
- Al publicar, los ficheros de `release.version_files` conservan sus finales de línea: un fichero con CRLF ya no se reescribe entero con LF. (SPEC-0003)
- Un patrón de `release.version_files` cuyo grupo de captura es opcional y no captura nada ya no corrompe el fichero al publicar: `mth release`, `mth hotfix finish` y `mth doctor` lo rechazan sin modificar nada. (SPEC-0003)

## [0.5.1] - 2026-11-18

### Corregido
- El plugin declara su versión real (0.5.1) en `plugin.json`, en el marketplace y en `mth --version`. La 0.5.0 se publicó declarando 0.4.0, así que Claude Code no ofrecía la actualización a quien ya tenía instalado el plugin: actualiza para recibir los cambios de la 0.5.0. (SPEC-0001, SPEC-0002)
- El CHANGELOG incluye la sección de la 0.5.0 (delegación verificable y niveles de modelo), que faltaba. (SPEC-0001, SPEC-0002)

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
