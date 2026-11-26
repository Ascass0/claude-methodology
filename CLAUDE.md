## Este repositorio se desarrolla a sí mismo

Este es el repositorio de desarrollo del plugin de metodología (`plugins/methodology/`), y a la vez **adopta y usa esa misma metodología** para desarrollarse (dogfooding). El plugin se implementa en el propio repo que lo desarrolla.

- La metodología que se te carga en cada sesión (principios, skills `mth-*`, hooks, agentes, script `mth`) es la **versión instalada del plugin** (caché de `~/.claude/plugins`), no el código de `plugins/methodology/` que estás modificando. Pueden diferir.
- Un cambio en `plugins/methodology/` puede alterar la herramienta con la que se desarrolla ese mismo cambio. Ten presente qué versión estás ejecutando y cuál estás editando, y no asumas que tus cambios ya están activos en la sesión.
- Esta sección es solo del repositorio de desarrollo: no forma parte del plugin ni debe copiarse a plantillas, docs de usuario ni a nada que se distribuya.

<!-- claude-methodology:start -->
## Metodología

Repo bajo **claude-methodology**: configuración en `.claude/methodology.toml`; los principios se cargan al iniciar cada sesión.

- Docs: `docs/` · Specs: `specs/features/` · ADRs: `specs/adr/<categoría>/`
- Fragmentos: `changes/` · Changelog: `CHANGELOG.md`
- Todo trabajo parte de una spec y pasa por las skills `mth-*`. Nunca se reescribe historia compartida.
<!-- claude-methodology:end -->
