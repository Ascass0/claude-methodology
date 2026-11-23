# Catálogo de agentes

Referencia operativa del catálogo de plantillas de agentes del plugin (`plugins/methodology/catalog/`). El diseño y las decisiones están en [SPEC-0012](../specs/features/SPEC-0012-catalogo-de-agentes.md) y [ADR-0008](../specs/adr/process/ADR-0008-catalogo-de-plantillas-de-agentes.md); el resumen y los límites, en el [README](../README.md#catálogo-de-agentes).

## Uso

| Comando | Qué hace |
|---|---|
| `mth agents list` | Agentes del catálogo con perfil, versión, `model_hint` y estado en el repo (no instalado, instalado, desactualizado, editado a mano, requisitos sin cumplir) |
| `mth agents add <agente>… \| --profile <perfil>` | Renderiza e instala; asegura el shim, la entrada de `.claude/settings.json` y `.gitignore`. No sobrescribe un agente propio sin cabecera salvo con `--replace`. No hace commits |
| `mth agents sync [<agente>…]` | Vuelve a renderizar con el catálogo actual y conserva la sección local. Se niega sin `--force` si se editó a mano la parte generada |
| `mth agents diff <agente>` | Diferencia entre lo instalado y lo que se renderizaría hoy |
| `mth agents remove <agente>` | Borra el agente y su guard y lo saca de `review.agents` y `[review.paths]`; con el último, quita también el shim y la entrada de `settings.json` |

Las variables de cada agente se fijan en `.claude/methodology.toml`:

```toml
[agents.lector-estado]
databases = { hermes = "data/hermes/state.db" }
max_rows = 100
```

Solo se admiten las claves declaradas en el `[vars]` del `meta.toml` del agente. Los perfiles están en `catalog/profiles.toml`. `mth doctor` avisa de agentes desactualizados, editados a mano o sin guard, y de una sección local obligatoria vacía.

## Formato de una plantilla

```
catalog/
├── profiles.toml                  # base | opcional | autonomo
├── _shared/                       # fragmentos .md, guards base y el shim
└── <agente>/
    ├── meta.toml
    ├── agent.md.tmpl
    ├── guard.toml
    └── evals.toml
```

### `meta.toml`

| Clave | Significado |
|---|---|
| `name`, `version`, `summary` | Identidad. `name` coincide con la carpeta |
| `kind` | `revisor`, `trabajador` o `principal` (hilo principal, se arranca con `claude --agent`) |
| `profiles` | Perfiles que lo incluyen |
| `origin` | De dónde viene el concepto (ver [Atribución](#atribución)) |
| `model_role` / `model_hint` | `review`, `task` o `none`; `model_hint` es solo informativo. Ninguna plantilla fija `model` en el frontmatter |
| `local_section` / `local_required` | Si lleva sección local y si `doctor` avisa cuando está vacía |
| `[requires]` | `config` (claves de `methodology.toml` que deben tener valor) y `vars` (variables obligatorias). Sin ellas, `add` no instala y dice qué falta |
| `[vars]` | Variables con su valor por defecto, sobrescribibles en `[agents.<agente>]` |
| `[review]` | Solo revisores: `order` (posición en `review.agents`; `verificador` va siempre primero), `branches` y `paths` (se añaden a `[review.paths]`) |

### `agent.md.tmpl`

Frontmatter y prompt. El frontmatter solo admite `name`, `description`, `tools` e `isolation`; ni `model` ni `hooks`. Sintaxis del cuerpo:

- `{{config.<clave.con.puntos>}}`: valor de `methodology.toml`.
- `{{vars.<nombre>}}`: variable del agente.
- `{{agent.name}}`, `{{agent.version}}`.
- `{{> fragmento}}`: incluye `catalog/_shared/<fragmento>.md`.

Una variable inexistente aborta el renderizado sin escribir nada. La misma entrada produce siempre los mismos bytes.

**Sección local.** El texto entre `<!-- mth:local:begin -->` y `<!-- mth:local:end -->` es del repo (modelo de amenazas, umbrales, convenciones). `sync` lo conserva.

**Cabecera.** Tras el frontmatter, `<!-- mth:template <agente>@<versión> sha256=<hash> -->`. El hash cubre el `.md` sin cabecera ni sección local, más el guard renderizado; así se detecta la edición manual. La cabecera también marca al agente como del catálogo para el guard.

### `guard.toml`

Obligatorio en todos los agentes. Admite `extends = "_shared/<guard>.toml"`; lo propio sobrescribe lo heredado. Se renderiza con las mismas variables (`{{vars.*}}`) en `.claude/mth/agents/<agente>.guard.toml`.

`[bash]`:

| Clave | Significado |
|---|---|
| `mode` | `allowlist` (cada segmento del comando debe empezar por un prefijo de `allow`), `denylist` (se rechaza lo que empiece por un prefijo de `deny`) o `deny` (sin Bash) |
| `allow` / `deny` | Prefijos de comando |
| `allow_exact` | Comandos admitidos solo tal cual, sin más argumentos (`git branch -r`: con `-d` borraría) |
| `filters` | Programas admitidos tras un `\|` en `allowlist` (`grep`, `head`, `wc`…). También se les aplica `deny_flags`; `sort` no admite `-o`, `--output`, `--compress-program` ni `-T` (ni sus abreviaturas), y `uniq` no admite ficheros |
| `deny_operators` | Subcadenas prohibidas en cualquier parte del comando, comillas incluidas (`>`, `$(`, `` ` ``, `<(`) |
| `deny_flags` | Opciones prohibidas en los segmentos de `allow` (`--output`, `--ext-diff`, `-F`…) |

Siempre se rechazan, además: asignaciones de entorno delante del programa (`GIT_EXTERNAL_DIFF=…`), `git -c`, `--config-env`, `--exec-path` y un `&` suelto.

En `allowlist`, el guard razona sobre el comando ya tokenizado, así que rechaza lo que la shell cambiaría después:

- un programa con ruta (`./git`, `/tmp/x/git`), salvo el `mth` del propio plugin (`sh <plugin>/scripts/mth`, `python <plugin>/scripts/mth.py`) o `$MTH`;
- `$` fuera de comillas simples (`$'…'`, `$VAR`) y las comillas invertidas;
- llaves, `~` y comodines (`*`, `?`, `[`) fuera de comillas: un `git diff *` expandiría a los nombres de fichero del repo, que pueden empezar por `--`.

Para texto literal, comillas simples: `git grep -n 'a.*b' -- '*.py'`.

`[write]` (Write, Edit, MultiEdit, NotebookEdit):

- `allow`: globs de rutas permitidas, relativos a la raíz del proyecto. Sin `[write]`, no se escribe.
- `in_worktree = true`: solo se escribe desde un worktree vinculado y dentro de él, nunca en el árbol principal. Lo llevan los agentes con `isolation: worktree` que escriben.
- Nunca, aunque `allow` sea `**`: `.git`, `.claude/hooks/`, `.claude/mth/`, `.claude/agents/`, `.claude/settings*.json` ni `.claude/methodology.toml`. Un agente no puede relajar sus propias restricciones.

`delegate = "global"`: el guard por agente no restringe al agente y se le aplica el guard global de la sesión. Solo lo puede declarar un agente de tipo `principal` (`orquestador`).

Un agente sin `Bash`, `Write` ni `Edit` declara `[bash] mode = "deny"` como defensa por si alguien amplía sus `tools`. Los guards comunes son `_shared/guard-revisor.toml` (git de solo lectura y filtros de texto) y `_shared/guard-trabajador.toml` (denylist que protege la historia, el remoto y el flujo de `mth`).

### `evals.toml`

| Tabla | Qué comprueba | Cómo se ejecuta |
|---|---|---|
| `[[guard]]` | Que un comando (o una escritura con `tool` y `path`) se permite o se bloquea (`expect = "allow" \| "deny"`) | **Determinista**: lo ejecuta `tests/test_agent_guard.py` contra el guard renderizado |
| `[[scope]]` (revisores) | Que, dado un `diff`, el revisor encuentra lo que debe (`must_find`) y no lo que no le toca | Con modelo: lo ejecutará un arnés aparte |
| `[[routing]]` (trabajadores) | Que un `prompt` se enruta al agente (`expect`) o no (`expect_not`) | Con modelo |
| `[[output]]` | Formato de la salida | Con modelo |
| `[[behavior]]` (`orquestador`) | Comportamiento en una sesión (`setup`, `must`) | Con modelo |

El arnés con modelo todavía no está en el repo. `tests/test_catalog.py` solo exige los mínimos de formato: todo agente tiene casos `[[guard]]`; los revisores, al menos dos `[[scope]]`; los trabajadores, al menos dos `[[routing]]`; el principal, algún `[[behavior]]`.

## Dónde queda cada cosa en el repo

| Fichero | Versionado | Contenido |
|---|---|---|
| `.claude/agents/<agente>.md` | sí | El agente renderizado, con cabecera y sección local |
| `.claude/mth/agents/<agente>.guard.toml` | sí | Las reglas del guard, renderizadas |
| `.claude/hooks/mth-agent-guard` | sí | El shim, común a todos los agentes |
| `.claude/settings.json` | sí | Una entrada `PreToolUse` (matcher `Bash\|Write\|Edit\|MultiEdit\|NotebookEdit`) que invoca el shim; se conservan las demás claves |
| `.gitignore` | sí | `.claude/worktrees/`, si hay agentes con `isolation: worktree` |
| `<git-common-dir>/mth/agent-guard.jsonl` | no | Una línea JSON por cada decisión sobre un agente del catálogo (agente, herramienta, comando o ruta, resultado, categoría, sesión; traceback si es un error interno). Se rota a `.1` al pasar de 1 MiB |
| `<git-common-dir>/mth/launcher` | no | Dos líneas: el intérprete de Python (≥ 3.11) y la ruta de `mth.py`. La escribe `mth session` en cada sesión, porque la ruta del plugin cambia con cada versión. Está en el git-common-dir para que funcione desde un worktree |

Flujo de una llamada: el shim lee el payload; si no trae `agent_id` ni `agent_type` (sesión principal), sale con 0 sin lanzar Python. Con un subagente llama a `mth agent-guard`, que deja pasar a los agentes que no son del catálogo (`methodology:verificador`, `Explore`, los propios del repo sin cabecera ni guard) y aplica su guard a los del catálogo. Un agente es del catálogo si su `.md` tiene cabecera de plantilla **o** existe su guard: si alguien borra la cabecera al adaptarlo a mano, queda bloqueado hasta `mth agents sync --force` o `mth agents remove`. Sin lanzador (plugin ausente o anterior a 0.8.0), el shim bloquea solo a los agentes del catálogo y a los que no puede identificar. El shim y el guard acotan su tiempo (5 s por llamada a `git`, 20 s el guard; la entrada del hook, 30 s): si vence, bloquean. Sale con 0 (permite) o 2 (bloquea, motivo en stderr con el prefijo `[mth-agent-guard]`). Falla cerrado ante cualquier error; la tabla de fallos está en SPEC-0012.

## Los 12 agentes

Datos de los `meta.toml` y `guard.toml` del catálogo.

| Agente | Tipo | Perfil | Tools | Guard | Requisitos |
|---|---|---|---|---|---|
| `revisor-seguridad` | revisor | base | Read, Grep, Glob, Bash | allowlist de git de solo lectura (`_shared/guard-revisor`) | ninguno; `local_required` (modelo de amenazas) |
| `revisor-fallos` | revisor | base | Read, Grep, Glob, Bash | ídem | ninguno |
| `revisor-adr` | revisor | base | Read, Grep, Glob, Bash | ídem | `paths.adr` |
| `revisor-diseno` | revisor | base | Read, Grep, Glob, Bash | ídem | ninguno |
| `revisor-parsimonia` | revisor | base | Read, Grep, Glob, Bash | ídem | ninguno |
| `diagnosticador` | trabajador | base | Read, Grep, Glob, Bash, Edit, Write; `isolation: worktree` | denylist (`_shared/guard-trabajador`); escritura solo en su worktree | `commands.test` |
| `explorador-specs` | trabajador | base | Read, Grep, Glob | `[bash] mode = "deny"` | `paths.specs`, `paths.adr` |
| `ingeniero-rendimiento` | trabajador | opcional | Read, Grep, Glob, Bash, Edit, Write; `isolation: worktree` | denylist; escritura solo en su worktree | variable `bench` |
| `analista-evals` | trabajador | opcional | Read, Grep, Glob, Bash, Write | denylist; escritura solo en `{{vars.reports}}/**` (por defecto `.work/evals`) | variable `results`; `local_required` |
| `lector-estado` | trabajador | opcional | Read, Bash | allowlist: solo `mth db-query` (+ `head`, `wc`) | variable `databases` |
| `respondedor-incidencias` | trabajador | opcional | Read, Grep, Glob, Bash | allowlist de git y `gh` de solo lectura; `gh api` sin `--method`, `-f`, `-F`, `--field`, `--input`… | ninguno (`upstream_remote` opcional) |
| `orquestador` | principal | autonomo | todas (sin `tools` en el frontmatter) | `delegate = "global"` | ninguno |

Los revisores tienen `review.order` 10 (seguridad), 20 (fallos), 25 (adr), 30 (diseño) y 40 (parsimonia), y se exigen en `feat`, `fix` y `hotfix`; `revisor-adr` solo cuando el diff toca ADR, dependencias, contenedores, esquemas o workflows (se amplía en `[review.paths]`). `orquestador` es experimental.

### `mth db-query`

`mth db-query --db <alias> [--schema | "<SQL>"]` resuelve el alias en `[agents.lector-estado].databases` y rechaza cualquier otro. Garantiza la solo lectura en tres capas: abre la base con `mode=ro`, activa `PRAGMA query_only` y usa un authorizer que solo admite lectura (rechaza escrituras, `ATTACH`, `load_extension` y varias sentencias). Devuelve como máximo `max_rows` filas, marca el truncado y corta la consulta a los `timeout_s` segundos. Con SQLite en WAL, `mode=ro` necesita poder crear o leer el fichero `-shm`.

## Prueba de humo

Comprueba que Claude Code envía `agent_id` y `agent_type` al hook y que el guard bloquea de verdad. Es la única forma de detectar que el guard ha pasado a fallar abierto (ADR-0008). Repítela al actualizar Claude Code y antes de cada versión del plugin. Última verificación: Claude Code 2.1.330.

1. Crea un repositorio desechable con un remoto local y un commit:

   ```
   git init --bare /tmp/humo-remoto.git
   git init -b main /tmp/humo && cd /tmp/humo
   git remote add origin /tmp/humo-remoto.git
   git commit --allow-empty -m "chore: init" && git push -u origin main
   ```

2. Adopta la metodología (`mth init`) y ejecuta `mth agents add revisor-seguridad`. Haz un commit con los ficheros instalados.
3. Abre una sesión de Claude Code en ese repo. El hook de sesión registra el lanzador en `<git-common-dir>/mth/launcher`; sin él, el shim bloquearía a todo subagente.
4. Pide que lance el subagente `revisor-seguridad` y que ejecute con él, por este orden:
   - `ls -la` → debe bloquearse con `[mth-agent-guard] …` (no está en la allowlist).
   - `git push --dry-run` → debe bloquearse con `[mth-agent-guard] …`.
   - `git status` → debe permitirse.
5. Si `ls -la` o `git push --dry-run` se ejecutan, el guard no está actuando: Claude Code ya no envía `agent_id`/`agent_type`, o la entrada de `.claude/settings.json` no se aplica. No publiques la versión ni confíes en el guard hasta resolverlo.

## Atribución

Los nombres de rol y varios principios de diseño de los agentes proceden del artículo «I built 100 Claude Code subagents — these are the 12 that actually earn their context» (S. Khaitan, dev.to). No se ha copiado texto: los prompts son propios. El campo `origin` de cada `meta.toml` registra el concepto de partida de cada agente.
