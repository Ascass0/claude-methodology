# ADR-0008 · Catálogo de plantillas de agentes instaladas en el repositorio

- Estado: aceptado
- Fecha: 2026-11-23
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

[SPEC-0012](../../features/SPEC-0012-catalogo-de-agentes.md) quiere que todo repo con la metodología tenga los revisores y trabajadores que PRINCIPLES §10 da por supuestos, adaptados a su caso, sin escribirlos a mano. Fuerzas en juego:

- **Enrutado.** Cada agente activo añade su `description` a las opciones de delegación de la sesión principal. Con muchos agentes cuyas descripciones se solapan, el router elige mal o no elige ninguno.
- **Restricciones.** La lista `tools` de un agente no restringe qué hace `Bash`. Claude Code ignora `hooks`, `mcpServers` y `permissionMode` en los agentes de un plugin. Además, en Claude Code 2.1.330 **tampoco se aplican los hooks del frontmatter de los agentes de `.claude/agents/`** cuando se ejecutan como subagentes. Se comprobó con una prueba de humo: un agente cuyo hook `PreToolUse` registra la llamada y sale con 2 ejecutó `git push` sin que el hook llegara a invocarse.
- **Identidad del subagente.** En esa misma versión, los hooks `PreToolUse` de `.claude/settings.json` sí se ejecutan para las llamadas de los subagentes. Su payload incluye `agent_id` y `agent_type`, que es el `name` del agente. En la sesión principal esas claves no aparecen. Cuando el agente usa `isolation: worktree`, el `cwd` del payload es su worktree.
- **Adaptación.** Un agente útil depende del repo: sus rutas, su comando de tests, su modelo de amenazas, sus bases de estado.
- **Determinismo** (PRINCIPLES §2): lo que puede hacer el código no se delega en un modelo.
- **Mínimo privilegio** (§2): un revisor no escribe y un trabajador no toca la historia de git.
- **Actualización.** Las mejoras del catálogo deben poder llegar a los repos sin que pierdan lo que añadieron.
- **Modelo por agente:** [ADR-0002](ADR-0002-niveles-de-modelo.md) lo saca del frontmatter de los agentes compartidos.

## Decisión

1. El plugin incluye un **catálogo de plantillas** (`catalog/`) que no está activo. Solo `verificador` y `documentador` siguen activos en `agents/`.
2. **`mth agents add` instala** en `.claude/agents/` los agentes elegidos, renderizados de forma **determinista** a partir de la configuración del repo y de `[agents.<agente>]`. Sin modelo de lenguaje.
3. Cada agente instalado lleva una **cabecera con su versión y un hash** de la parte generada (el `.md` sin la sección local, más su guard), y una **sección local** que el repo rellena y que `sync` conserva.
4. **Las restricciones se aplican con un único hook del repo que despacha por `agent_type`.**
   - Al instalar el primer agente, `mth agents add` añade a `.claude/settings.json`, que va versionado, una entrada `PreToolUse` con matcher `Bash|Write|Edit|MultiEdit|NotebookEdit`. La entrada invoca el shim versionado `.claude/hooks/mth-agent-guard`.
   - El shim no lanza Python si el payload no tiene ni `agent_id` ni `agent_type`, es decir, en la sesión principal.
   - Con un subagente, el shim llama a `mth agent-guard`, que lee `agent_type`:
     - si no es un agente instalado desde el catálogo (sin cabecera de plantilla), lo deja pasar;
     - si lo es, aplica sus reglas de `.claude/mth/agents/<agente>.guard.toml`.
   - Las plantillas **no declaran `hooks`** en el frontmatter.
5. **Todo agente del catálogo tiene guard.** Un agente sin `Bash`, `Write` ni `Edit` lleva `[bash] mode = "deny"`, como defensa por si alguien amplía sus `tools`. El agente principal (`orquestador`) declara `delegate = "global"`: el guard por agente no lo restringe y le aplica el guard global. Un agente con cabecera de plantilla y sin guard se bloquea.
6. Los agentes con `isolation: worktree` escriben con `[write] in_worktree = true`. Solo pueden escribir dentro del worktree vinculado desde el que trabajan, y nunca en el árbol de trabajo principal, aunque Claude Code dejara de aplicar el aislamiento. El `cwd` de cada llamada tiene que pertenecer al mismo repositorio (mismo `git-common-dir`).
7. El guard por agente **falla cerrado** con cualquier subagente: le faltan las reglas, el lanzador o el shim, el JSON es ilegible, llega un `agent_id` sin `agent_type` o hay un error interno. El guard global sigue fallando abierto, porque actúa sobre toda la sesión y GitHub es la capa que hace cumplir las reglas sobre las ramas compartidas. Las dos políticas viven en entradas, módulos y ficheros distintos; ninguna reutiliza el punto de entrada de la otra.
8. El agente `lector-estado` no usa la CLI `sqlite3`. Usa **`mth db-query`**, que garantiza la solo lectura en tres capas: la URI `mode=ro`, `query_only` y un authorizer.
9. Las plantillas **no fijan `model`** (ADR-0002). Los revisores toman `models.review` y los trabajadores `models.task`.

## Alternativas consideradas

- **Hook `PreToolUse` en el frontmatter de cada agente** (propuesta inicial): Claude Code 2.1.330 no lo ejecuta para los subagentes; la prueba de humo dejó pasar un `git push`. Se descarta. Si una versión futura lo aplica, no aporta nada que el despacho por `agent_type` no cubra, y tener los dos mecanismos duplicaría el coste.
- **El despacho por `agent_type` en el `hooks.json` del plugin**: separa peor las dos políticas y, sobre todo, falla abierto si el plugin se desactiva o se desinstala, porque el hook desaparece con él. Con el hook en el repo, las restricciones viajan con los agentes instalados: sin plugin, el shim no encuentra el lanzador y bloquea a los subagentes del catálogo. Se descarta.
- **Extender el guard global con `agent_type`:** mezcla una política que falla abierto con otra que falla cerrado en el mismo punto de entrada. Se descarta.
- **Agentes activos en el `agents/` del plugin:** no se pueden restringir, no se adaptan a cada repo y todos entran en el enrutado de todos los repos. Se descarta.
- **Adaptar las plantillas con un LLM al instalarlas:** cada repo acabaría con un texto distinto que no se puede comparar, versionar ni actualizar, e incumple «Determinismo». Se descarta. Lo que de verdad depende del dominio va en la sección local, que se rellena en el PR de adopción.
- **Enlaces simbólicos a las plantillas del plugin:** la ruta del plugin cambia con cada versión, los enlaces se rompen en cada clon y no hay dónde adaptar el agente. Se descarta.
- **Un único `revisor-codigo` para §2 a §5:** el prompt sería muy largo y las revisiones, superficiales. Se divide en `revisor-fallos` (§2 fallo, §3, §4) y `revisor-diseno` (SOLID, STUPID, §5).
- **Un agente `ejecutor-tests`:** ejecutar tests y resumir sus fallos es determinista; incumple §2 «Determinismo» y §10. Se descarta.

## Consecuencias

- **Positivas:**
  - un repo nuevo tiene los revisores de §10 con un solo comando;
  - las restricciones de cada agente se aplican de verdad (verificado en Claude Code 2.1.330);
  - siguen aplicándose aunque falte el plugin;
  - las mejoras del catálogo llegan con `sync` y un PR;
  - la edición manual se detecta.
- **Negativas:**
  - hay más superficie que mantener, porque cada plantilla trae evals y guard;
  - `mth` modifica `.claude/settings.json`, un fichero que también edita la persona. La fusión conserva las demás claves, pero puede cambiar el formato del fichero;
  - el hook se ejecuta en todas las llamadas a `Bash`, `Write` y `Edit` de la sesión, no solo en las de los agentes. En el prototipo costó unos 3 ms en la sesión principal (sin Python) y unos 48 ms por llamada de un subagente del catálogo;
  - las copias instaladas se quedan desactualizadas si nadie ejecuta `sync`, aunque `doctor` avisa.
- **Riesgos aceptados:**
  - **Dependencia de `agent_type`.** El mecanismo depende de un campo del payload de Claude Code. Si una versión dejara de enviar `agent_id` y `agent_type`, el shim trataría las llamadas como de la sesión principal y los agentes del catálogo funcionarían sin restricciones, sin aviso: fallaría abierto. No hay forma determinista de detectarlo desde el repo. Se mitiga con una prueba de humo documentada que se repite al actualizar Claude Code y antes de cada versión del plugin.
  - Un `disableAllHooks` en la configuración de Claude Code desactiva el guard; `doctor` lo avisa si aparece en la configuración del repo.
  - El guard en modo denylist no es una frontera de seguridad: un script lanzado por el agente puede hacer cualquier cosa, también un `git push`. Las fronteras reales son `isolation: worktree` para el árbol de trabajo y los rulesets de GitHub para las ramas compartidas.
