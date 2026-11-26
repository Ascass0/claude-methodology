# SPEC-0012 · Catálogo de agentes instalables

- Estado: implementada
- Fecha: 2026-11-23
- Formato: compacto
- ADRs: [ADR-0008](../adr/process/ADR-0008-catalogo-de-plantillas-de-agentes.md)
- Sustituye a: —


## Contexto

- Cada repo que adopta la metodología escribe a mano sus revisores y trabajadores: se repite el trabajo, los agentes divergen y nada garantiza que un repo nuevo tenga los que PRINCIPLES §10 da por supuestos.
- Meter agentes activos en el `agents/` del plugin no lo resuelve: entran en el enrutado de todos los repos, no se adaptan a ninguno y no se pueden restringir.
- En Claude Code 2.1.330 los hooks del frontmatter no se aplican a los subagentes; sí los de `.claude/settings.json`, que reciben `agent_type`.
- Decisión y prueba que la sustenta: [ADR-0008](../adr/process/ADR-0008-catalogo-de-plantillas-de-agentes.md).

## Objetivo

1. El plugin incluye un catálogo de plantillas de agentes.
2. `mth` instala en el repo los agentes elegidos, adaptados de forma determinista a su configuración.
3. Las restricciones de cada agente las aplica un guard que identifica al subagente por `agent_type` y falla cerrado.
4. `mth` mantiene los agentes al día sin perder lo que el repo añadió y detecta la edición manual de la parte generada.

## Fuera de alcance

- Adaptar un agente con un modelo de lenguaje. El renderizado es determinista.
- Variantes en inglés de las plantillas. Las plantillas están en español; si `language.docs = "en"`, `mth agents add` avisa.
- El arnés que ejecuta los evals con modelo (`[[scope]]`, `[[routing]]`, `[[output]]`, `[[behavior]]`). Va en una spec aparte; aquí solo se exige su formato.
- `mth test --summary`.
- Que el guard por agente sea una frontera frente a un agente malicioso: es una salvaguarda frente a errores.
- Un modelo distinto por agente (`[models.agents]`): primero se mide (PRINCIPLES §2, «Optimización con evidencia»).

## Comportamiento

### Catálogo (en el plugin)

```
plugins/methodology/catalog/
├── profiles.toml                 # base | opcional | autonomo
├── _shared/                      # fragmentos {{> ...}}, guards base, shim mth-agent-guard.sh
└── <agente>/
    ├── meta.toml                 # versión, tipo, perfiles, requisitos, vars, [review]
    ├── agent.md.tmpl             # frontmatter + prompt con {{config.*}}, {{vars.*}}, {{> fragmento}}
    ├── guard.toml                # obligatorio en todos los agentes
    └── evals.toml                # [[guard]] deterministas + evals con modelo
```

- **Frontmatter de las plantillas.** Solo admite `name`, `description`, `tools` e `isolation`; ni `model` ni `hooks`.
- **`guard.toml`.** Todos los agentes lo llevan:
  - un agente sin `Bash`, `Write` ni `Edit` declara `[bash] mode = "deny"` y no tiene `[write]`;
  - solo un agente de tipo `principal` puede declarar `delegate = "global"`, que deja sin efecto el guard por agente;
  - un agente con `isolation: worktree` que escribe declara `[write] allow = ["**"]` e `in_worktree = true`.

### Configuración (`.claude/methodology.toml`)

Nueva tabla opcional `[agents.<agente>]` con las variables del agente (`bench`, `databases`...).

- Cada agente solo admite las claves declaradas en el `[vars]` de su `meta.toml`; cualquier otra clave es un error, igual que en el resto de la configuración.
- Sigue la regla de [SPEC-0009](SPEC-0009-actualizacion-del-plugin-con-configuracion-mas-nueva.md): una versión anterior del plugin la rechaza como clave desconocida.

### Instalación (en el repo, versionado)

| Fichero | Contenido |
|---|---|
| `.claude/agents/<agente>.md` | El agente renderizado. Tras el frontmatter lleva la cabecera `<!-- mth:template <agente>@<versión> sha256=<hash> -->`. |
| `.claude/mth/agents/<agente>.guard.toml` | Las reglas del guard, renderizadas. |
| `.claude/hooks/mth-agent-guard` | El shim, común a todos los agentes. |
| `.claude/settings.json` | Una entrada `PreToolUse` (ver más abajo). Se conservan las demás claves del fichero. |
| `.gitignore` | `.claude/worktrees/`, si hay algún agente con `isolation: worktree`. Ahí crea Claude Code sus worktrees, y un `git add -A` los añadiría como repos embebidos. |
| `<git-common-dir>/mth/launcher` | **No versionado.** La ruta del lanzador vigente; la escribe `mth session`. |

El hash cubre el `.md` sin la cabecera y sin el contenido de la sección local (`<!-- mth:local:begin -->` … `<!-- mth:local:end -->`), más el guard renderizado.

La entrada de `.claude/settings.json`:

- tiene matcher `Bash|Write|Edit|MultiEdit|NotebookEdit`;
- se identifica por invocar `.claude/hooks/mth-agent-guard`, así que añadirla es idempotente;
- su comando ejecuta el shim si existe; si no existe y el payload es de un subagente, bloquea (exit 2).

### Despacho del guard

1. **Shim.** Si el payload no contiene `agent_id` ni `agent_type` (sesión principal), sale con 0 sin lanzar `mth`. En caso contrario:
   - lee el lanzador de `<git-common-dir>/mth/launcher`;
   - si no es un repositorio git, sale con 2;
   - si no encuentra el lanzador (plugin ausente o anterior a 0.8.0), bloquea solo a los subagentes del catálogo (`.claude/mth/agents/<agente>.guard.toml` o cabecera de plantilla) y a los que no puede identificar; si `agent_type` aparece más de una vez en el payload (un dato anidado de una herramienta), no se puede identificar y bloquea; los demás (`verificador`, `Explore`...) siguen funcionando;
   - si lo encuentra, le pasa el payload con `agent-guard`, acotado en tiempo con `timeout` o, si no existe (macOS), con `perl`; cualquier salida distinta de 0, también por tiempo agotado, bloquea. Si el guard muere por tiempo, el shim añade una línea al registro.
2. **`mth agent-guard`.** Lee el JSON del hook por stdin:
   - **sin `agent_type`** (pero con `agent_id`): bloquea;
   - **`agent_type` que no es un agente del catálogo**: permite. Es del catálogo un nombre válido de plantilla que tiene **cabecera de plantilla en `.claude/agents/<agente>.md` o un `.claude/mth/agents/<agente>.guard.toml`**. Quedan fuera los agentes del plugin (`methodology:verificador`), los integrados (`Explore`) y los propios del repo sin cabecera ni guard;
   - **agente del catálogo**: aplica `.claude/mth/agents/<agente>.guard.toml`. Si no existe, bloquea y pide `mth agents sync`. Si existe el guard pero el `.md` perdió la cabecera, bloquea con «agente del catálogo editado: mth agents sync o remove»: un agente adaptado a mano no queda sin restricciones (ADR-0008, decisión 7);
   - cada decisión sobre un agente del catálogo, y cada bloqueo de un subagente sin identificar, se registra (también los que decide el shim: sin lanzador, o con una salida inesperada del guard; sin repositorio o sin `timeout` ni `perl` no hay dónde escribir con seguridad y solo queda el mensaje) en `<git-common-dir>/mth/agent-guard.jsonl` (JSON por línea: agente, herramienta, programa y subcomando o ruta, resultado, categoría, motivo, `session_id`; con traceback si es un error interno). No guarda el comando completo y redacta credenciales en el motivo y en el traceback (§4 «Secretos nunca»), también en formato JSON (`"password": "x"`) y tras `Authorization: token`. Los cortes que registra el shim llevan la misma correlación (hora, agente, sesión, herramienta) y cubren cualquier código de salida inesperado del guard, no solo el tiempo. El fichero se crea con permisos 0600 y se rota al superar 1 MiB;
   - las llamadas a `git` del guard tienen timeout, y el guard entero un límite propio; si vencen, bloquea;
   - sale con 0 para permitir y con 2 para bloquear, con el motivo en stderr. Falla cerrado ante cualquier error;
   - semántica de `[bash]` y de `[write] allow`: la de `mthlib/agent_guard.py`, portada de la implementación de referencia de la entrega; se documenta en [docs/catalogo-de-agentes.md](../../docs/catalogo-de-agentes.md). En modo `allowlist`, además:
     - el programa no puede llevar ruta (`./git`, `/x/git`), salvo el `mth` del propio plugin con ruta absoluta (`sh <plugin>/scripts/mth`, `python <plugin>/scripts/mth.py`) o `$MTH`;
     - se bloquea toda expansión de shell que el tokenizador no modela: `$` fuera de comillas simples (salvo `$MTH` como programa), comillas invertidas, llaves, `~` y comodines (`*`, `?`, `[`) fuera de comillas;
     - `deny_flags` cubre también las abreviaturas de las opciones largas (`git grep --open=sh` es `--open-files-in-pager`) y las cortas agrupadas (`git grep -nOsh`, `gh api -iXPOST`, `jq -nf`): se deniega si el grupo contiene la letra de una opción prohibida, aunque a veces sea un falso positivo (fail-closed);
     - en los filtros tras `|` se aplican también `deny_flags`, y no se admiten las opciones que escriben o ejecutan (`sort -o/--output/--compress-program/-T`), ficheros posicionales en `uniq` ni lecturas del entorno o de módulos en `jq` (`env`, `$ENV`, `input_filename`, `import`, `include`, `-f`, `--rawfile`, `--slurpfile`). Riesgo aceptado: un filtro (`jq`, `grep`, `head`...) puede recibir un fichero posicional y leerlo; no da nada que el agente no tenga ya con `Read`;
     - `~` solo cuenta como expansión al inicio de una palabra (`HEAD~1` se admite);
   - `[write]` nunca permite escribir en `.git`, `.claude/hooks/`, `.claude/mth/`, `.claude/agents/`, `.claude/settings*.json` ni `.claude/methodology.toml`, aunque `allow` sea `**`: un trabajador no puede relajar sus propias restricciones. La comparación no distingue mayúsculas, porque macOS y Windows resuelven `.Claude/Hooks` al mismo fichero.
3. **Raíz y worktrees.** El `cwd` del payload tiene que pertenecer al mismo repositorio que `CLAUDE_PROJECT_DIR` (mismo `git-common-dir`); si no, se bloquea.
   - Con `in_worktree = true`, la escritura solo se permite si el `cwd` está en un worktree vinculado, no en el árbol principal, y la ruta queda dentro de ese worktree.
   - Sin `in_worktree`, los globs de `[write] allow` son relativos a la raíz del proyecto.

### Comandos

- **`mth agents list`**: cada agente del catálogo con su perfil, su versión, su `model_hint` y su estado en el repo. Los estados posibles son:
  - no instalado;
  - instalado (vX.Y.Z);
  - desactualizado (catálogo vX.Y.Z);
  - editado a mano;
  - requisitos sin cumplir, con la clave que falta.
- **`mth agents add <agente>… | --profile <perfil>`**: renderiza e instala, y asegura el shim, la entrada de `.claude/settings.json` y, si hace falta, la línea de `.gitignore`.
  - Un agente con requisitos sin cumplir no se instala; se dice por qué y con qué clave.
  - Si es revisor, lo inserta en `review.agents` según `review.order` (verificador primero) y añade sus `paths` a `[review.paths]`, si tiene.
  - Si el agente ya existe y no viene del catálogo (no tiene cabecera), no lo sobrescribe sin `--replace`.
  - Valida y renderiza todo antes de escribir el primer fichero.
  - No hace commits: los hace la sesión, como cualquier otro cambio.
- **`mth agents sync [<agente>…]`**: vuelve a renderizar con la versión actual del catálogo y conserva la sección local. Si la parte generada fue editada a mano, se niega sin `--force` y muestra el diff.
- **`mth agents diff <agente>`**: diferencia entre lo instalado y lo que renderizaría hoy.
- **`mth agents remove <agente>`**: borra el `.md` y el guard, y lo saca de `review.agents` y de `[review.paths]`. Si era el último agente del catálogo, quita también la entrada de `.claude/settings.json` y el shim.
- **`mth agent-guard`**: el guard por agente (ver «Despacho del guard»). No reutiliza el punto de entrada del guard global, que falla abierto.
- **`mth db-query --db <alias> [--schema | "<SQL>"]`**: consulta SQLite de solo lectura sobre los alias de `[agents.lector-estado].databases`, con `max_rows` y timeout. La ruta de cada base debe quedar dentro del repositorio (resuelta, sin `..` ni enlaces que salgan); `max_rows` y `timeout_s` deben ser positivos; la longitud de un valor está limitada (`SQLITE_LIMIT_LENGTH`) y cada celda se recorta en la salida. Semántica: `mthlib/db_query.py`, portada de la implementación de referencia de la entrega.

### Integración con lo existente

- **`mth session`** escribe en `<git-common-dir>/mth/launcher` la ruta del lanzador vigente, igual que reescribe el hook `commit-msg`.
- **`mth init`** ofrece el perfil `base` en la pregunta de revisores, con todo marcado salvo lo que no cumpla sus requisitos. Las variables obligatorias de los agentes opcionales se piden al añadirlos.
  - La pregunta `revisores` pasa a hacerse en todos los perfiles, también en un repo nuevo sin agentes; si no, justo los repos nuevos se quedarían sin catálogo. Se corrige [SPEC-0004](SPEC-0004-adopcion-guiada.md) en consecuencia.
  - La respuesta admite `catalog` (agentes del catálogo) y `vars` (sus variables). `mth init` comprueba requisitos y colisiones antes de tocar nada e instala los agentes en la rama de adopción, en el mismo commit.
  - En la reestructuración ([SPEC-0011](SPEC-0011-reestructuracion-guiada-de-la-metodologia.md)) no se admite `catalog`: un repo adoptado gestiona sus agentes con `mth agents`.
- **`mth doctor`** comprueba, y todos sus avisos son ⚠:
  - que cada agente instalado tiene su guard;
  - que existen el shim y la entrada de `.claude/settings.json`;
  - que hay un lanzador registrado;
  - que no hay agentes desactualizados ni editados a mano;
  - que la sección local obligatoria (`local_required`) no está vacía;
  - que `.claude/settings.json` no declara `disableAllHooks`;
  - que no hay agentes del catálogo instalados con `language.docs = "en"`.
- **Skill `mth-review`**: lanza los revisores en el orden de `review.agents`.
- **Skill `mth-develop`**: nombra `explorador-specs` antes de planificar features o cambios estructurales, y `diagnosticador` ante fallos de causa desconocida.
- **Modelo:** ninguna plantilla fija `model` ([ADR-0002](../adr/process/ADR-0002-niveles-de-modelo.md)). Los revisores usan `models.review` y los trabajadores `models.task`. `model_hint` solo se muestra en `mth agents list`.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Variable de plantilla inexistente | Renderizado (`TemplateError`): se aborta sin escribir nada (fail-fast) | AC-02 |
| FM-02 | Requisito sin configurar (`requires`) | `mth agents add`: no se instala y dice qué clave falta | AC-03 |
| FM-03 | Clave desconocida en `[agents.<agente>]` | Carga de la configuración: error que nombra la clave y el agente | AC-19 |
| FM-04 | Agente del catálogo cuyo `.md` perdió la cabecera (guard presente) | `mth agent-guard` bloquea: «agente del catálogo editado»; `doctor` avisa del guard sin cabecera | AC-21 |
| FM-05 | Cabecera de plantilla sin guard | `mth agent-guard` y `doctor`: bloquea y pide `mth agents sync`; `doctor` avisa | AC-21 |
| FM-06 | Plugin ausente o anterior a 0.8.0 (sin lanzador) | Shim: bloquea a los subagentes del catálogo o sin identificar y lo registra; los demás siguen | AC-22 |
| FM-07 | `git` o el guard no responden a tiempo | Timeouts del guard y del shim: bloquea (exit 2) antes de que venza el timeout del hook; el shim registra el corte | AC-24 |
| FM-08 | No hay `timeout` en el sistema (macOS sin coreutils) | Shim: usa `perl` para acotar; el guard tiene además su propio límite (`signal.alarm`) | AC-24 |
| FM-09 | No hay `timeout` ni `perl` | Shim: bloquea a los subagentes con un mensaje accionable (instalar coreutils o perl); sin límite que lo corte, no arriesga que el hook venza y la llamada pase | AC-24 |
| FM-10 | El guard muere por una causa distinta de un bloqueo (excepción antes de `main`, importación, señal) | Shim: bloquea y lo registra con categoría `crash` | AC-24 |
| FM-11 | `mth agents` no puede escribir un fichero (disco lleno, permisos) | Error con el fichero y cómo reanudar, no un «bug»; la operación es reanudable | AC-17 |
| FM-12 | No se puede escribir el registro de decisiones | `mth agent-guard`: la decisión se aplica igual con aviso en stderr; una prueba de humo que dependa del registro falla, así que no pasa inadvertido | AC-27 |
| FM-13 | Programa con ruta, expansión de shell o filtro que escribe en un agente de allowlist | `mth agent-guard` bloquea | AC-23 |
| FM-14 | Escritura de un trabajador en los ficheros que definen sus restricciones | `mth agent-guard` bloquea, aunque `allow` lo cubra | AC-25 |
| FM-15 | Fallo a mitad de `mth agents add` | Orden de escritura: shim y entrada del hook antes que los agentes, cada fichero de forma atómica; nunca queda un agente instalado sin guard | AC-17 |
| FM-16 | Parte generada editada a mano | Hash de la cabecera: `sync` se niega sin `--force`; `doctor` avisa | AC-06 |
| FM-17 | Agente del repo con el mismo nombre, sin cabecera | `mth agents add` no sobrescribe sin `--replace` | AC-07 |
| FM-18 | `.claude/settings.json` ilegible | `mth agents add` / `remove` abortan sin escribir nada | AC-17 |
| FM-19 | Faltan las reglas del guard de un agente del catálogo | `mth agent-guard` bloquea (exit 2) y pide `mth agents sync` | AC-08 |
| FM-20 | No hay lanzador (plugin desinstalado, sesión sin hook) | Shim con payload de subagente: bloquea (exit 2) y pide abrir una sesión nueva | AC-10 |
| FM-21 | Falta el shim | Comando de la entrada de `settings.json`: bloquea a los subagentes (exit 2); la sesión principal sigue | AC-22 |
| FM-22 | JSON ilegible, `agent_id` sin `agent_type`, comando no tokenizable, error interno | `mth agent-guard` bloquea (exit 2) | AC-08 |
| FM-23 | `cwd` fuera del repositorio | `mth agent-guard` bloquea | AC-18 |
| FM-24 | Escritura de un agente `in_worktree` fuera de su worktree o desde el árbol principal | `mth agent-guard` bloquea, aunque Claude Code no aplique el aislamiento | AC-18 |
| FM-25 | Comando «de lectura» que ejecuta código (`git -c`, `GIT_*=`, `--ext-diff`, `sqlite3 .shell`) | El guard bloquea | AC-23 |
| FM-26 | Worktrees de Claude Code sin ignorar | `mth agents add` añade `.claude/worktrees/` a `.gitignore` | AC-17 |
| FM-27 | Consulta que escribe, `ATTACH`, varias sentencias, `load_extension` | `mth db-query` (mode=ro + query_only + authorizer) rechaza sin tocar la base | AC-11 |
| FM-28 | Consulta lenta o enorme | `mth db-query` corta por tiempo, devuelve como máximo `max_rows` y marca el truncado, limita la longitud de los valores y recorta las celdas | AC-12, AC-26 |
| FM-29 | Alias que apunta fuera del repositorio, o límites no positivos | `mth db-query` rechaza sin abrir la base | AC-26 |
| FM-30 | Plugin antiguo con `[agents]` en la configuración | Carga de la configuración (SPEC-0009): rechaza la clave desconocida; no trabaja sin entenderla | AC-19 |
| FM-31 | Claude Code deja de enviar `agent_id`/`agent_type` | No detectable desde el repo: riesgo aceptado (ADR-0008), prueba de humo al actualizar Claude Code y antes de cada versión (SPEC-0014) | — |
| FM-32 | Una plantilla, un guard o el shim del catálogo citan un ID de spec o ADR del propio plugin | El repo adoptado no lo define y `mth trace` falla, bloqueando su integración: los ficheros que se instalan NO llevan IDs internos y un test lo comprueba | AC-28 |

## Criterios de aceptación

- **AC-01**: CUANDO se renderiza el mismo agente con la misma configuración, `mth` DEBE producir los mismos bytes.
- **AC-02**: SI una plantilla usa una variable inexistente, ENTONCES el renderizado DEBE abortar sin escribir ficheros.
- **AC-03**: SI un agente tiene requisitos sin cumplir, ENTONCES `mth agents add` NO DEBE instalarlo y DEBE nombrar la clave que falta.
- **AC-04**: CUANDO se añade un revisor con `mth agents add`, `mth` DEBE insertarlo en `review.agents` según su `review.order` (con `verificador` primero) y añadir sus `paths` a `[review.paths]`.
- **AC-05**: CUANDO se ejecuta `mth agents sync`, `mth` DEBE conservar el contenido de la sección local.
- **AC-06**: SI la parte generada no coincide con el hash de su cabecera, ENTONCES `mth agents sync` DEBE negarse sin `--force`.
- **AC-07**: SI existe un agente del repo sin cabecera de plantilla, ENTONCES `mth agents add` NO DEBE sobrescribirlo salvo con `--replace`.
- **AC-08**: SI faltan las reglas de un agente del catálogo, el JSON es ilegible, el payload trae `agent_id` sin `agent_type` o hay un error interno, ENTONCES `mth agent-guard` DEBE devolver 2.
- **AC-09**: Todos los casos `[[guard]]` de `catalog/*/evals.toml` DEBEN dar el resultado esperado.
- **AC-10**: CUANDO el payload no trae `agent_id` ni `agent_type`, el shim DEBE salir con 0 sin invocar el lanzador; SI con un payload de subagente no existe `<git-common-dir>/mth/launcher`, ENTONCES DEBE bloquear (exit 2); DEBE funcionar desde un worktree vinculado.
- **AC-11**: SI una consulta de `mth db-query` escribe, usa `ATTACH`, varias sentencias o `load_extension`, ENTONCES DEBE rechazarla sin modificar la base.
- **AC-12**: `mth db-query` DEBE rechazar los alias no declarados y devolver como máximo `max_rows` filas.
- **AC-13**: CUANDO hay agentes desactualizados, agentes editados a mano, una sección local obligatoria vacía o falta la entrada de `.claude/settings.json`, `mth doctor` DEBE avisar.
- **AC-14**: CUANDO se ejecuta `mth agents remove`, `mth` DEBE borrar los ficheros del agente y sacarlo de `review.agents` y de `[review.paths]`; al quitar el último agente del catálogo, DEBE eliminar también la entrada de `.claude/settings.json` y el shim.
- **AC-15**: Ninguna plantilla del catálogo DEBE declarar `model` ni `hooks` en su frontmatter; todas DEBEN tener `guard.toml`; `delegate = "global"` DEBE aparecer solo en agentes de tipo `principal`.
- **AC-16**: `mth agent-guard` DEBE permitir las llamadas de un `agent_type` que no es del catálogo y aplicar las reglas del guard a los que sí lo son.
- **AC-17**: CUANDO se ejecuta `mth agents add`, `mth` DEBE añadir la entrada de `.claude/settings.json` una sola vez conservando las demás claves; SI el fichero es ilegible, ENTONCES NO DEBE escribir nada.
- **AC-18**: MIENTRAS `in_worktree = true`, el guard DEBE permitir escribir dentro del worktree vinculado del `cwd` y bloquear escribir desde el árbol principal, fuera del worktree o con un `cwd` de otro repositorio.
- **AC-19**: SI `[agents.<agente>]` tiene una clave que no está en el `[vars]` del agente, ENTONCES la carga de la configuración DEBE fallar nombrando la clave.
- **AC-20**: CUANDO `mth init --answers` incluye agentes en `catalog`, `mth` DEBE instalarlos en el commit de adopción; SI alguno no puede instalarse (requisitos, colisión, nombre desconocido), ENTONCES NO DEBE cambiar nada.
- **AC-21**: SI un agente con guard instalado tiene un `.md` sin cabecera de plantilla, ENTONCES DEBE quedar bloqueado (exit 2, «agente del catálogo editado») y `mth doctor` DEBE avisar de los guards sin cabecera y de las cabeceras sin guard.
- **AC-22**: SI no hay lanzador, ENTONCES el shim DEBE bloquear a los subagentes del catálogo y a los no identificables y dejar pasar a los demás.
- **AC-23**: MIENTRAS el modo es `allowlist`, `mth agent-guard` DEBE bloquear los programas con ruta (salvo el `mth` del plugin), las expansiones de shell sin comillas, las abreviaturas y grupos de opciones cortas prohibidas y las opciones de filtros que escriben, ejecutan o leen el entorno.
- **AC-24**: SI `git` no responde a tiempo durante la decisión o el guard entero no termina a tiempo (con `timeout`, con `perl` o por su propio límite), ENTONCES `mth agent-guard` DEBE bloquear y el shim DEBE registrarlo; sin `timeout` ni `perl`, el shim DEBE bloquear.
- **AC-25**: `[write]` NO DEBE permitir nunca escribir en `.git`, `.claude/hooks/`, `.claude/mth/`, `.claude/agents/`, `.claude/settings*.json` ni `.claude/methodology.toml`.
- **AC-26**: SI un alias de `mth db-query` apunta fuera del repositorio o un límite no es positivo, ENTONCES DEBE rechazarlo; DEBE recortar las celdas largas.
- **AC-27**: CUANDO `mth agent-guard` decide sobre un agente del catálogo, DEBE registrar la decisión en `<git-common-dir>/mth/agent-guard.jsonl`, con traceback si es un error interno, sin el comando completo ni credenciales, con permisos 0600 y rotación al superar 1 MiB.
- **AC-28**: Las plantillas, los guards y el shim del catálogo NO DEBEN contener IDs de specs ni ADR del plugin: lo que `mth agents add` instala NO DEBE hacer fallar `mth trace` en un repo que no los define.

## Notas

- La validación de referencia de la entrega (`check_catalog.py`, no versionada) pasó a `tests/test_catalog.py` y `tests/test_agent_guard.py`, con `verifies:` sobre esta spec.
- La prueba de humo que dio origen al diseño se hizo en Claude Code 2.1.330 con `claude -p`. Su procedimiento queda en la documentación del catálogo para repetirlo al actualizar Claude Code.
- Origen de los conceptos: el artículo *I built 100 Claude Code subagents* (S. Khaitan, dev.to). Se reutilizan los nombres de rol y los principios de diseño; no se copia texto.
