# Changelog

Todos los cambios relevantes de este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Los cambios pendientes de publicar viven como fragmentos en `changes/` y se incorporan aquí al publicar cada versión.

<!-- mth:releases -->

## [0.1.0] - 2026-11-10

### Añadido
- Principios de desarrollo con precedencia explícita y mecanismo de imposición por regla.
- CLI determinista `mth`: ramas, commits validados, sync, integración por PR con merge commit, releases y hotfixes reanudables.
- Trazabilidad: IDs definidos y únicos, referencias, enlaces internos y cobertura de criterios de aceptación.
- Changelog por fragmentos agregado en cada versión.
- Hooks de Claude Code: contexto de sesión y guard contra reescritura de historia.
- Skills `mth-*` para todo el ciclo.
