---
bump: minor
refs: SPEC-0012, ADR-0008
---
### Añadido
- Catálogo de 12 plantillas de agentes (cinco revisores, `diagnosticador`, `explorador-specs`, cuatro opcionales y el `orquestador` experimental) en tres perfiles: `base`, `opcional` y `autonomo`. No están activas: `mth agents list|add|sync|diff|remove` las instala en `.claude/agents/`, renderizadas de forma determinista con la configuración y `[agents.*]`, y las mantiene al día conservando la sección local de cada repo. Los revisores se colocan en `review.agents` según su orden. Guía en `docs/catalogo-de-agentes.md`.
- Guard por agente: `mth agents add` deja una entrada `PreToolUse` en `.claude/settings.json` y el shim `.claude/hooks/mth-agent-guard`; `mth agent-guard` aplica a cada agente del catálogo sus propias reglas y falla cerrado. `mth session` registra el lanzador que usa el shim.
- `mth db-query --db ALIAS`: consultas SQLite estrictamente de solo lectura para el agente `lector-estado`, con límite de filas y de tiempo.
- `mth init` ofrece el perfil `base` en la pregunta `revisores`, y `mth doctor` avisa de agentes desactualizados, editados a mano o sin guard.

### Cambiado
- La pregunta `revisores` de la adopción se hace en todos los perfiles, también en un repo nuevo sin agentes.
- Nueva tabla opcional `[agents.*]` en `.claude/methodology.toml`. Un plugin anterior a esta versión la rechaza como clave desconocida: actualiza el plugin en todo el equipo antes de añadirla.
