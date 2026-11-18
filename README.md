# claude-methodology

Metodología de desarrollo autónomo dirigido por specs para Claude Code, distribuida como plugin. Aterriza los [principios](plugins/methodology/PRINCIPLES.md) en tres capas:

1. **Scripts deterministas** (`mth`): todo lo mecánico (ramas, commits, integración, versiones, changelog, trazabilidad) lo hace código que valida y bloquea, no instrucciones en prosa.
2. **Hooks**: en un repo adoptado, al iniciar sesión se inyectan las reglas base y el estado del repo; antes de cada comando de shell, un guard bloquea lo que rompe el flujo o reescribe historia.
3. **Skills** `mth-*`: guían a Claude por cada fase y llaman a los scripts. Claude las usa sin pedir permiso.

El criterio (diseño, calidad, documentación) queda en los principios y en los agentes revisores de cada repositorio.

## Contenido

```
claude-methodology/
├── .claude-plugin/marketplace.json   # este repo es su propio marketplace
├── plugins/methodology/
│   ├── PRINCIPLES.md                 # principios completos (RFC 2119)
│   ├── context/core.md               # reglas base inyectadas en cada sesión
│   ├── hooks/hooks.json              # SessionStart + PreToolUse(Bash)
│   ├── scripts/mth.py, mthlib/       # CLI determinista (Python ≥ 3.11, sin dependencias)
│   ├── skills/mth-*/SKILL.md         # develop, init, spec, branch, commit, review, integrate, release, trace
│   ├── agents/                       # agentes compartidos: verificador, documentador
│   └── templates/                    # config, spec, ADR, CHANGELOG, bloque de CLAUDE.md
└── tests/                            # tests unitarios y de extremo a extremo (gh simulado)
```

## Requisitos

- Python ≥ 3.11 instalado (no hace falta que sea el `python3` activo: el lanzador `scripts/mth` busca uno válido aunque pyenv o un venv apunten a otra versión; `MTH_PYTHON` lo fija), git y [GitHub CLI](https://cli.github.com/) autenticado (`gh auth login`).
- Un repositorio en GitHub con `main` y al menos un commit.

## Instalación

1. Publica este repositorio en GitHub (por ejemplo, `<owner>/claude-methodology`).
2. En Claude Code: `/plugin marketplace add <owner>/claude-methodology` y `/plugin install methodology@claude-methodology`.
3. En cada repositorio, la skill `mth-init` (o `mth init --marketplace-repo <owner>/claude-methodology --github`) deja la activación del plugin en su `.claude/settings.json`, de modo que cualquier clon lo carga.

Fija la versión del plugin por repositorio: un cambio de metodología se adopta con un PR en cada repo, no de forma implícita en todos a la vez.

> La sintaxis de marketplaces y `enabledPlugins` evoluciona; verifícala en la [documentación de plugins de Claude Code](https://docs.claude.com/en/docs/claude-code/plugins-reference).

## Actualizar el plugin

Una versión nueva acepta la configuración de las anteriores: las claves que añade son opcionales y sus valores por defecto mantienen el comportamiento previo. Al revés no ocurre lo mismo. Un plugin antiguo rechaza las claves que no conoce, porque ignorarlas sería inseguro: un plugin que no entendiera `autonomy.level = "supervised"` trabajaría sin supervisión ([SPEC-0009](specs/features/SPEC-0009-actualizacion-del-plugin-con-configuracion-mas-nueva.md)).

Orden seguro en un equipo:

1. Cada persona actualiza el plugin (`/plugin`) y abre una sesión nueva de Claude Code. La sesión en curso sigue usando la versión con la que arrancó: el contexto, el guard y la ruta de `mth` se fijan al iniciar.
2. Cuando todo el equipo esté actualizado, las claves nuevas se añaden a `.claude/methodology.toml` en un PR.

Si alguien se adelanta, quien siga con la versión anterior verá `Clave desconocida en la configuración: '<clave>' (claude-methodology X.Y.Z no la reconoce)`. Ningún comando `mth` se ejecuta y su hook `commit-msg` rechaza los commits hasta que actualice. Las versiones anteriores a la 0.6.0 muestran solo "Revisa la ortografía".

Actualizar no toca ficheros versionados del repo. Las ramas a medias, los fragmentos y las revisiones registradas siguen valiendo. El hook `commit-msg` apunta a la carpeta de la versión instalada y el hook de sesión lo reinstala en cada sesión nueva. Si se hace un commit tras actualizar y antes de abrir sesión, y la versión antigua ya no está en la caché, el hook lo rechaza con `claude-methodology no encontrado`: basta con abrir una sesión nueva.

## Adopción en un repositorio

Mientras un repositorio no tiene `.claude/methodology.toml`, el plugin está inactivo: el hook de sesión solo avisa de que se puede adoptar y el guard no bloquea nada ([SPEC-0004](specs/features/SPEC-0004-adopcion-guiada.md), [ADR-0003](specs/adr/process/ADR-0003-adopcion-guiada-por-perfiles-de-destino.md)).

La adopción es una entrevista guiada, con la skill `mth-init`:

1. `mth survey` inventaria el repo sin modificarlo (ramas, specs y ADR existentes, agentes, hooks, herramientas de release, CI).
2. Opus presenta la metodología y pregunta solo lo que el inventario no resuelve.
3. `mth init --answers <json>` convierte las respuestas en `.claude/methodology.toml` y en el ADR de adopción.
4. Si no se quiere adoptar, `mth init --decline` desactiva el plugin en ese repo (`.claude/settings.local.json`, no versionado).

`mth init` sin `--answers` sigue existiendo y adopta con la plantilla por defecto:

- crea `development` desde `main` si no existe;
- abre `chore/adopt-methodology` con `.claude/methodology.toml`, `docs/`, `specs/features/`, `specs/adr/`, `changes/`, `CHANGELOG.md` (con marcador de versiones) y un bloque gestionado en `CLAUDE.md` (el resto del fichero no se toca);
- instala el hook `commit-msg` (según `hooks.commit_msg` si ya había uno);
- con `--github`: solo merge commits en el repo y un ruleset que protege `main` y `development` (PR obligatorio, sin borrado ni force-push).

Después se ajusta `.claude/methodology.toml` (comando de tests, esquema de IDs, revisores, roles, prefijos de rama propios), se comprueba con `mth doctor` y se integra con `mth integrate`. En una adopción gradual, `trace.legacy_base` evita que el contenido anterior bloquee la trazabilidad; `mth trace --legacy` lo lista.

### Configuración

| Clave | Para qué |
|---|---|
| `commands.test` / `precommit` | Tests (gate de integración y release) y comprobación rápida antes de cada commit |
| `paths.*` | Ubicación de docs, specs, ADR, fragmentos, changelog, tests y del fichero donde mth escribe su bloque para Claude (`claude_md`) |
| `[ids.<TIPO>]` | Esquema de IDs trazables: `pattern` y dónde se definen (`defined_in`). Ejemplo para el fork: `[ids.F] pattern = 'F-\d{3}'`, `defined_in = ["docs/02-*.md"]` |
| `branches.extra` | Prefijos propios (`sync`, `security`, `purge`) con su flujo: `feature` o `hotfix` |
| `commits.require_refs` | Tipos de commit que deben referenciar spec, ADR o issue |
| `commits.external_refs` | Refs de historia externa (upstream) cuyos commits no se validan ni se listan |
| `changes.required_for` | Ramas que aportan fragmento de changelog |
| `review.agents` / `required_for` | Agentes revisores del repo (en orden de precedencia) y ramas que exigen revisión |
| `roles.*` | Agentes del repo para coder, documentador y verificador |
| `models.*` | Escalera de reintento (`ladder`, por defecto `haiku`, `sonnet`, `opus`) y nivel de las tareas sin modelo (`task`), de los revisores (`review`) y del documentador (`documenter`). Ver [SPEC-0002](specs/features/SPEC-0002-niveles-de-modelo.md); `mth models` los muestra |
| `ci.required` | Exigir CI en verde en cada PR (fail-safe) |
| `trace.*` | Comprobaciones activas, ficheros incluidos (`include`) y exclusiones justificadas |
| `trace.legacy_base` | Commit de la adopción gradual: los hallazgos en ficheros sin cambios desde él son avisos y `mth trace --legacy` los lista. Ver [SPEC-0005](specs/features/SPEC-0005-modo-legado-en-la-trazabilidad.md) |
| `hooks.commit_msg` | Qué hacer con un hook `commit-msg` ajeno: `own` (lo deja), `replace` (instala el de mth) o `chain` (lo ejecuta antes de validar). Ver [SPEC-0006](specs/features/SPEC-0006-hooks-commit-msg-encadenados.md) |
| `autonomy.level` | `full` (por defecto), `until-pr` (integrar y publicar piden confirmación) o `supervised` (además, ramas, commits y push). Ver [SPEC-0007](specs/features/SPEC-0007-autonomia-configurable.md) y [ADR-0004](specs/adr/process/ADR-0004-autonomia-configurable-por-repositorio.md) |
| `language.docs` | Idioma de docs, specs, ADR, changelog y PR: `es` (por defecto) o `en`. Código y commits, siempre en inglés. Ver [SPEC-0008](specs/features/SPEC-0008-idioma-de-la-documentacion-configurable.md) |
| `release.*` | Release de GitHub, firma y prefijo de las etiquetas (`tag_prefix`) y ficheros que declaran la versión (`version_files`: `path` y `pattern` con un grupo de captura), que `release` y `hotfix finish` actualizan en el commit de la versión y `doctor` verifica. Ver [SPEC-0003](specs/features/SPEC-0003-ficheros-de-version-en-la-publicacion.md) |
| `work.dirs` | Subdirectorios propios del repo en `.work/`, además de los de serie. Ver [Directorio de trabajo local](#directorio-de-trabajo-local) |

### Directorio de trabajo local

Cada repo adoptado tiene `.work/` en su raíz: ahí deja Claude lo que produce mientras trabaja y no es parte del repo. Se excluye de git con una línea `/.work/` en `.git/info/exclude`, así que el plugin no modifica ningún fichero versionado ([SPEC-0010](specs/features/SPEC-0010-directorio-de-trabajo-local.md), [ADR-0006](specs/adr/process/ADR-0006-directorio-de-trabajo-local-excluido-de-git.md)).

| Subdirectorio | Contenido |
|---|---|
| `plans/` | planes de trabajo, manifiestos de agentes y borradores de diseño |
| `merge-request/` | títulos, resúmenes y cuerpos de PR |
| `security-report/` | informes de seguridad |
| `reviews/` | informes completos de los revisores |
| `notes/` | notas de sesión que se conservan |
| `tmp/` | temporales desechables: se pueden borrar en cualquier momento |

El hook de sesión lo crea y lo excluye en cada sesión (también `mth init` al adoptar), y `mth doctor` lo comprueba. Si git ya versiona algo bajo `.work/`, no se toca y `doctor` lo marca con ✗. El guard bloquea los `git add` forzados que lo incluirían (`git add -f .work/…`, `git add -f .`, `git add -f -A`). La exclusión es de cada clon: no viaja con el repo, pero cada sesión la restablece.

### Uso en un fork

Un fork convive con la historia, los tags y los ficheros de upstream. Prepara la configuración fuera del repo y adóptala con `mth init --config <fichero>`, de modo que nada se escriba en rutas de upstream:

- `paths.*` bajo un directorio propio (por ejemplo, `fork/`) y `paths.claude_md = ".claude/CLAUDE.md"`.
- `commits.external_refs = ["refs/remotes/upstream/main"]`: las sincronizaciones por merge no validan commits ajenos.
- `release.tag_prefix` propio (por ejemplo, `"fork-v"`): las versiones no chocan con los tags de upstream.
- `trace.include` limitado a lo propio: la documentación de upstream no se comprueba.

## De la regla al mecanismo

| Regla | Mecanismo |
|---|---|
| Toda feature parte de una spec | `mth integrate` exige que el fragmento de una `feat` referencie su spec |
| Cada AC tiene test | `mth trace`: una spec `implementada` sin `verifies: SPEC/AC` falla |
| IDs únicos y referencias válidas | `mth trace` (también tras `mth sync`, donde aparecen las colisiones de ramas paralelas) |
| Enlaces internos válidos y dentro del repo | `mth trace` |
| Conventional Commits + cuerpo + `Refs:` | `mth commit`, hook `commit-msg`, revalidación en `mth integrate` |
| Modelo de ramas y ramas hijas | `mth branch` (nombres validados; hijas con `--`) |
| Hijas integradas antes que la padre | `mth integrate` |
| Merge commit, nunca squash ni rebase | `mth integrate` / `release` + guard + ajustes de GitHub |
| Sin reescritura de historia | Guard (force-push, rebase, `--no-verify`, borrado de tags) + ruleset |
| Revisión del HEAD final sin bloqueantes | `mth review record --report` toma los bloqueantes del informe del revisor (por SHA) + `mth integrate` |
| Un revisor que no termina no cuenta como aprobado | `mth review record`: un informe ausente, vacío, de más de 256 KiB o que no acaba en `BLOQUEANTES: <n>` no se registra y la revisión sigue pendiente |
| Cada agente delegado solo toca su alcance | `mth plan verify`: los ficheros de cada manifiesto, dentro de los permitidos de su tarea; ningún cambio sin dueño ni declarado sin cambios reales |
| Las tareas paralelas no se solapan | `mth plan check` / `mth trace`: dos tareas de la misma oleada no comparten ficheros (entre globs, en caso de duda, solapan) |
| Un agente caído no cuenta como trabajo hecho | `mth plan verify`: una tarea sin manifiesto válido queda "no ejecutada" y la oleada no se acepta |
| Cada tarea con el modelo que necesita | Columna `Modelo` del plan (validada por `mth plan check`) y `mth plan model` |
| Un reintento no repite el modelo que falló | `mth plan model --retry`: siguiente nivel de `models.ladder` |
| Niveles ajustados con evidencia | Eventos `plan.task` de `mth plan verify` y resumen por modelo con `mth plan stats` |
| Tests en verde en cada integración | `mth integrate` / `release` / `hotfix finish` |
| CI en verde | `gh pr checks` con espera, fail-safe si no hay CI y `ci.required` |
| Changelog sin conflictos | Fragmentos por rama; `mth release` los agrega (Keep a Changelog) |
| SemVer y etiquetas | `mth release` calcula la versión del mayor `bump`; etiqueta anotada |
| `main ⊆ development` | El merge de vuelta integra `main` en `development` tras cada versión |
| Adopción sin conflictos silenciosos | `mth survey` + entrevista de `mth-init` + `mth init --answers`; sin adoptar, el plugin no actúa |
| Artefactos de trabajo fuera del repo | `.work/` excluido en `.git/info/exclude` por el hook de sesión y `mth init`; guard ante `git add` forzado; `mth doctor` |
| Trazabilidad de las operaciones | `.git/mth/trace.jsonl` (eventos JSON con ID de ejecución) |
| Diseño, excepciones, parsimonia, docs en código | Principios + revisores del repo (criterio) |

## Agentes

El plugin incluye dos agentes compartidos por todos los repos:

- **`verificador`**: primer revisor de cada rama. Comprueba que cada criterio y cada modo de fallo de la spec están implementados y cubiertos por un test que de verdad lo comprueba, ejecuta los tests, confirma que un fix trae su test de regresión y detecta afirmaciones falsas en commits, changelog y docs.
- **`documentador`**: actualiza docs, fragmento de changelog y los registros documentales que exija el repo, en español y sin duplicar fuentes de verdad.

Cada repo añade en `.claude/agents/` sus **agentes de implementación** (`dev-*`), especializados por área, y sus revisores específicos. La sesión principal orquesta. Si delega dos o más tareas, el reparto es la sección `## Plan de trabajo` de la spec: tareas agrupadas en oleadas, con sus ficheros permitidos y sus criterios, que `mth plan check SPEC-NNNN` valida antes de lanzar nada. Las tareas de una oleada se ejecutan en paralelo; cada `dev-*` recibe un encargo autocontenido y devuelve un manifiesto JSON. Al cerrar la oleada, `mth plan verify SPEC-NNNN --wave N --manifest <fichero> …` contrasta los manifiestos con el plan y con los cambios reales del árbol de trabajo. Cada tarea lleva su modelo (columna `Modelo` del plan o `models.task`) y `mth plan model` da el alias que se pasa a la herramienta Agent. Una tarea no ejecutada o no completada se relanza una sola vez, con el nivel siguiente de la escalera (`mth plan model --retry`); si vuelve a fallar, la sesión principal la implementa o rehace el plan. Con `mth plan verify --model T-NN=alias` queda registrado qué modelo ejecutó cada tarea y `mth plan stats` resume los resultados por modelo. Los revisores y el documentador se lanzan con `models.review` y `models.documenter`. Los commits los hace siempre la sesión principal, al cerrar cada oleada. El formato del plan y del manifiesto está en [SPEC-0001](specs/features/SPEC-0001-delegacion-verificable.md) y la decisión, en [ADR-0001](specs/adr/process/ADR-0001-plan-y-manifiesto-verificados.md); los niveles de modelo, las métricas y su formato, en [SPEC-0002](specs/features/SPEC-0002-niveles-de-modelo.md) y [ADR-0002](specs/adr/process/ADR-0002-niveles-de-modelo.md); el protocolo, en la skill `mth-develop`.

Cada revisor termina su informe con la línea `BLOQUEANTES: <n>`. La sesión principal guarda el informe tal cual y lo registra con `mth review record <agente> --report <informe> --summary "…"`; el número de bloqueantes sale del informe, no se escribe a mano.

Los revisores del repo se declaran en `review.agents` (en orden de precedencia). Con `[review.paths]`, un revisor de un área solo se exige cuando el diff la toca, lo que mantiene acotado el coste de cada integración. En Claude Code, los agentes de plugin pueden aparecer con el prefijo `methodology:`.

## Autonomía y permisos

Por defecto (`autonomy.level = "full"`), la metodología no pide permiso para ramas, commits, integraciones ni versiones. El plugin **no** cambia el modo de permisos de Claude Code: eso se decide en cada repositorio. Para que no haya confirmaciones, configura `.claude/settings.json` del repo (por ejemplo, `defaultMode: acceptEdits` y reglas `allow` para `Bash(git:*)`, `Bash(gh:*)` y `Bash(python3:*)`; verifica la sintaxis en la [documentación de permisos](https://docs.claude.com/en/docs/claude-code/iam)) o ejecuta Claude dentro de un sandbox o devcontainer.

Si un repositorio necesita supervisión, elige `until-pr` o `supervised` en `autonomy.level`: el guard pide la confirmación de la persona ([SPEC-0007](specs/features/SPEC-0007-autonomia-configurable.md)).

## Límites conocidos

- **El guard no es una frontera de seguridad.** Analiza el texto del comando; un comando ofuscado lo evade. La imposición real sobre `main` y `development` es el ruleset de GitHub. Si el guard falla, deja pasar (fail-open documentado) para no paralizar al agente.
- **Rulesets:** requieren permisos de administración y, en repositorios privados, un plan de GitHub que los incluya. Si no se pueden aplicar, `mth init --github` avisa y el flujo local sigue imponiendo las mismas reglas.
- **Las tareas de una oleada comparten árbol de trabajo:** no se aíslan en worktrees, así que un agente puede ver ficheros a medio escribir por otro. Los cambios fuera de alcance se detectan al cerrar la oleada con `mth plan verify`, no al escribirlos.
- **Las revisiones se registran en `.git/mth/`** (local): no viajan entre máquinas. Su resumen queda en la descripción del PR.
- **Las métricas de modelo son locales:** `mth plan stats` lee `.git/mth/trace.jsonl`, que no viaja entre máquinas. Los alias de `models.*` son los de la herramienta Agent de Claude Code (`haiku`, `sonnet`, `opus`, `fable`).
- **No se puede verificar automáticamente** que un commit sea temático, que esté en inglés ni que una docstring sea suficiente: es criterio de quien desarrolla y de los revisores.
- **Hook `commit-msg`:** script `sh`; no probado en Windows nativo.
- **Perfil de lenguaje:** las reglas de código son genéricas. Los perfiles por lenguaje se añadirán como referencias de las skills cuando haya un segundo proyecto que los justifique.

## Desarrollo del plugin

```
sh tests/run.sh -v
```

`tests/run.sh` ejecuta los tests con el primer Python ≥ 3.11 que encuentra (`MTH_PYTHON` lo fija).

El test de extremo a extremo recorre adopción → feature con rama hija → revisión → CI en rojo y reanudación → release interrumpida y reanudada → hotfix, contra un remoto local y un `gh` simulado que produce merge commits reales.
