# ADR-0004 · Autonomía configurable por repositorio

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process
- Formato: compacto

## Contexto

- PRINCIPLES §11 fija la autonomía completa y deja la supervisión a un hook propio de cada repo; casi ningún repo lo escribe.
- La adopción guiada ([SPEC-0004](../../features/SPEC-0004-adopcion-guiada.md)) debe ofrecer niveles intermedios a equipos que no aceptan la autonomía completa desde el primer día.
- La autonomía se apoya en gates deterministas; pedir confirmación se suma a ellos, no los sustituye.
- Un hook `PreToolUse` puede responder `ask` y Claude Code lo muestra a la persona; en sesión no interactiva, `ask` equivale a denegar.
- El guard ya inspecciona cada comando Bash.

## Decisión

1. `[autonomy] level` DEBE admitir tres niveles: `full` (por defecto), `until-pr` (confirma integrar y publicar) y `supervised` (además, cada commit, rama nueva y push).
2. Lo DEBE aplicar el guard existente con la decisión `ask`, no instrucciones de contexto: una instrucción se olvida, un hook no.
3. SI el guard no puede leer la configuración, ENTONCES DEBE pedir confirmación como en `supervised` (fail-safe). Los comandos que no reconoce los deja pasar (fail-open), como hasta ahora.
4. PRINCIPLES §11 DEBE describir los tres niveles; el resto de reglas de autonomía no cambia.

## Rechazado

- Solo instrucciones en las reglas de sesión: no es verificable y se pierde al compactar el contexto.
- Hook de ejemplo para copiar: cada repo acabaría con una variante y la adopción no podría configurarlo.
- `permissions.ask` de `.claude/settings.json`: casa por prefijo y no reconoce las formas de invocar `mth` (`$MTH`, ruta completa, `python mth.py`).

## Consecuencias

- **+** Un equipo adopta con supervisión y la relaja cambiando una clave; la adopción guiada lo pregunta.
- **−** En `supervised` la sesión se interrumpe a menudo: es el precio de quien lo elige.
- **riesgo** El guard reconoce `mth` por su forma; una invocación muy indirecta (script propio) no pide confirmación → el guard es barrera para el agente, no frontera de seguridad; las reglas de GitHub protegen las ramas compartidas.

## Impone

- [script] `mthlib/guard.py`: decisión `ask` por nivel y fail-safe sin configuración; `mthlib/config.py`: `AUTONOMY_LEVELS`.
- [criterio] PRINCIPLES §11 y `revisor-adr`: el nivel sale de la configuración, no del contexto.
