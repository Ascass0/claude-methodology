# ADR-0008 · Catálogo de plantillas de agentes instaladas en el repositorio

- Estado: aceptado
- Fecha: 2026-11-23
- Categoría: process
- Formato: compacto

## Contexto

- [SPEC-0012](../../features/SPEC-0012-catalogo-de-agentes.md): todo repo con la metodología debe tener los revisores y trabajadores que PRINCIPLES §10 da por supuestos, adaptados a su caso, sin escribirlos a mano.
- Enrutado: cada agente activo añade su `description` a las opciones de delegación; con muchos y solapados el router elige mal.
- La lista `tools` de un agente no restringe qué hace `Bash`. Claude Code ignora `hooks`, `mcpServers` y `permissionMode` en los agentes de un plugin.
- En Claude Code 2.1.330 los hooks del frontmatter de los agentes de `.claude/agents/` tampoco se aplican como subagentes. Prueba de humo: un agente cuyo hook `PreToolUse` sale con 2 ejecutó `git push` sin invocarlo.
- Sí se ejecutan los hooks `PreToolUse` de `.claude/settings.json` para subagentes; su payload trae `agent_id` y `agent_type` (el `name` del agente), ausentes en la sesión principal. Con `isolation: worktree`, el `cwd` es el worktree.
- Un agente útil depende del repo: rutas, comando de tests, modelo de amenazas, bases de estado.
- Determinismo (§2): lo que puede hacer el código no se delega en un modelo. Mínimo privilegio (§2): un revisor no escribe; un trabajador no toca la historia.
- Las mejoras del catálogo deben llegar sin que los repos pierdan lo añadido.
- [ADR-0002](ADR-0002-niveles-de-modelo.md) saca el modelo del frontmatter de los agentes compartidos.
- Matizado por [ADR-0021](ADR-0021-planes-acordados-antes-de-desarrollar.md): `planificador` se suma a `verificador` y `documentador` como agente del plugin en `agents/`.

## Decisión

1. El plugin DEBE incluir un catálogo de plantillas (`catalog/`) no activo; solo `verificador` y `documentador` siguen activos en `agents/`.
2. `mth agents add` DEBE instalar en `.claude/agents/` los agentes elegidos, renderizados de forma determinista desde la configuración y `[agents.<agente>]`, sin modelo de lenguaje.
3. Cada agente instalado DEBE llevar cabecera con versión y hash de la parte generada (el `.md` sin la sección local, más su guard) y una sección local que `sync` conserva.
4. Las restricciones DEBEN aplicarse con un único hook del repo que despacha por `agent_type`:
   - al instalar el primer agente, `mth agents add` añade a `.claude/settings.json` (versionado) una entrada `PreToolUse` con matcher `Bash|Write|Edit|MultiEdit|NotebookEdit` que invoca el shim `.claude/hooks/mth-agent-guard`;
   - el shim NO DEBE lanzar Python si el payload no trae `agent_id` ni `agent_type` (sesión principal);
   - con un subagente llama a `mth agent-guard`: si no es un agente instalado desde el catálogo (sin cabecera de plantilla) lo deja pasar; si lo es, aplica `.claude/mth/agents/<agente>.guard.toml`;
   - las plantillas NO DEBEN declarar `hooks` en el frontmatter.
5. Todo agente del catálogo DEBE tener guard. Sin `Bash`, `Write` ni `Edit` lleva `[bash] mode = "deny"` por si se amplían sus `tools`. El principal (`orquestador`) declara `delegate = "global"` y recibe el guard global. Un agente con cabecera y sin guard DEBE bloquearse.
6. Los agentes con `isolation: worktree` DEBEN escribir con `[write] in_worktree = true`: solo dentro de su worktree vinculado, nunca en el árbol principal, y con `cwd` del mismo repositorio (mismo `git-common-dir`).
7. El guard por agente DEBE fallar cerrado con cualquier subagente: faltan reglas, lanzador o shim, JSON ilegible, `agent_id` sin `agent_type` o error interno. El guard global sigue fallando abierto (GitHub protege las ramas compartidas). Las dos políticas NO DEBEN compartir entrada, módulo ni fichero.
8. `lector-estado` NO DEBE usar la CLI `sqlite3`: DEBE usar `mth db-query`, de solo lectura en tres capas (URI `mode=ro`, `query_only`, authorizer).
9. Las plantillas NO DEBEN fijar `model` (ADR-0002): revisores toman `models.review`, trabajadores `models.task`.

## Rechazado

- Hook `PreToolUse` en el frontmatter de cada agente (propuesta inicial): Claude Code 2.1.330 no lo ejecuta para subagentes. Si una versión futura lo hace, el despacho por `agent_type` ya lo cubre y tener ambos duplicaría el coste.
- Despacho por `agent_type` en el `hooks.json` del plugin: separa peor las políticas y falla abierto si el plugin se desactiva, porque el hook desaparece con él. En el repo, las restricciones viajan con los agentes.
- Extender el guard global con `agent_type`: mezcla una política que falla abierto con otra que falla cerrado en el mismo punto de entrada.
- Agentes activos en el `agents/` del plugin: no se restringen, no se adaptan y entran en el enrutado de todos los repos.
- Adaptar con un LLM al instalar: textos distintos no comparables ni actualizables; incumple «Determinismo». Lo dependiente del dominio va en la sección local, rellenada en el PR de adopción.
- Enlaces simbólicos a las plantillas del plugin: la ruta cambia con cada versión, se rompen en cada clon y no admiten adaptación.
- Un único `revisor-codigo` (§2 a §5): prompt largo y revisiones superficiales. Se divide en `revisor-fallos` (§2 fallo, §3, §4) y `revisor-diseno` (SOLID, STUPID, §5).
- Agente `ejecutor-tests`: ejecutar tests y resumir fallos es determinista (§2, §10).

## Consecuencias

- **+** Un repo nuevo tiene los revisores de §10 con un comando; las restricciones se aplican de verdad (verificado en 2.1.330) y sin plugin; las mejoras llegan con `sync` y un PR; la edición manual se detecta.
- **−** Más superficie: cada plantilla trae evals y guard.
- **−** `mth` modifica `.claude/settings.json`, que también edita la persona: se conservan las demás claves, pero el formato puede cambiar.
- **−** El hook corre en toda llamada a `Bash`, `Write` y `Edit`: ~3 ms en la sesión principal (sin Python), ~48 ms por llamada de un subagente del catálogo.
- **−** Las copias se desactualizan si nadie ejecuta `sync`; `doctor` avisa.
- **riesgo** Dependencia de `agent_type`: si una versión dejara de enviar `agent_id` y `agent_type`, los agentes funcionarían sin restricciones y sin aviso → prueba de humo que se repite al actualizar Claude Code y antes de cada versión (ADR-0010).
- **riesgo** `disableAllHooks` desactiva el guard → `doctor` lo avisa si aparece en la configuración del repo.
- **riesgo** El guard denylist no es frontera de seguridad: un script del agente puede hacer un `git push` → fronteras reales: `isolation: worktree` y los rulesets de GitHub.

## Impone

- [script] `mthlib/agents.py` (`mth agents add|sync|diff|remove|list`), `mthlib/agent_guard.py` (guard por agente, falla cerrado), `mthlib/db_query.py` (`mth db-query`), `catalog/_shared/` (shim y guards base).
- [hook] `.claude/settings.json` → `.claude/hooks/mth-agent-guard`.
- [criterio] `mth doctor` (desactualizado, editado a mano, sin guard, `disableAllHooks`); `mth smoke` (prueba de humo).
