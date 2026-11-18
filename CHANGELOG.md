# Changelog

Todos los cambios relevantes de este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Los cambios pendientes de publicar viven como fragmentos en `changes/` y se incorporan aquí al publicar cada versión.

<!-- mth:releases -->

## [0.4.0] - 2026-11-18

### Añadido
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
