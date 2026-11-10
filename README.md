# claude-methodology

Metodología de desarrollo autónomo dirigido por specs para Claude Code, distribuida como plugin. Aterriza los [principios](plugins/methodology/PRINCIPLES.md) en tres capas:

1. **Scripts deterministas** (`mth`): todo lo mecánico (ramas, commits, integración, versiones, changelog, trazabilidad) lo hace código que valida y bloquea, no instrucciones en prosa.
2. **Hooks**: al iniciar sesión se inyectan las reglas base y el estado del repo; antes de cada comando de shell, un guard bloquea lo que rompe el flujo o reescribe historia.
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

## Adopción en un repositorio

`mth init`:

- crea `development` desde `main` si no existe;
- abre `chore/adopt-methodology` con `.claude/methodology.toml`, `docs/`, `specs/features/`, `specs/adr/`, `changes/`, `CHANGELOG.md` (con marcador de versiones) y un bloque gestionado en `CLAUDE.md` (el resto del fichero no se toca);
- instala el hook `commit-msg`;
- con `--github`: solo merge commits en el repo y un ruleset que protege `main` y `development` (PR obligatorio, sin borrado ni force-push).

Después se ajusta `.claude/methodology.toml` (comando de tests, esquema de IDs, revisores, roles, prefijos de rama propios), se comprueba con `mth doctor` y se integra con `mth integrate`.

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
| `ci.required` | Exigir CI en verde en cada PR (fail-safe) |
| `trace.*` | Comprobaciones activas, ficheros incluidos (`include`) y exclusiones justificadas |
| `release.*` | Release de GitHub, firma y prefijo de las etiquetas (`tag_prefix`) |

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
| Revisión del HEAD final sin bloqueantes | `mth review record` (por SHA) + `mth integrate` |
| Tests en verde en cada integración | `mth integrate` / `release` / `hotfix finish` |
| CI en verde | `gh pr checks` con espera, fail-safe si no hay CI y `ci.required` |
| Changelog sin conflictos | Fragmentos por rama; `mth release` los agrega (Keep a Changelog) |
| SemVer y etiquetas | `mth release` calcula la versión del mayor `bump`; etiqueta anotada |
| `main ⊆ development` | El merge de vuelta integra `main` en `development` tras cada versión |
| Trazabilidad de las operaciones | `.git/mth/trace.jsonl` (eventos JSON con ID de ejecución) |
| Diseño, excepciones, parsimonia, docs en código | Principios + revisores del repo (criterio) |

## Agentes

El plugin incluye dos agentes compartidos por todos los repos:

- **`verificador`**: primer revisor de cada rama. Comprueba que cada criterio y cada modo de fallo de la spec están implementados y cubiertos por un test que de verdad lo comprueba, ejecuta los tests, confirma que un fix trae su test de regresión y detecta afirmaciones falsas en commits, changelog y docs.
- **`documentador`**: actualiza docs, fragmento de changelog y los registros documentales que exija el repo, en español y sin duplicar fuentes de verdad.

Cada repo añade en `.claude/agents/` sus **agentes de implementación** (`dev-*`), especializados por área, y sus revisores específicos. La sesión principal orquesta: divide la spec en tareas con ficheros disjuntos, entrega a cada `dev-*` un encargo autocontenido y recibe un manifiesto; los commits los hace siempre la sesión principal (skill `mth-develop`, paso 4).

Los revisores del repo se declaran en `review.agents` (en orden de precedencia). Con `[review.paths]`, un revisor de un área solo se exige cuando el diff la toca, lo que mantiene acotado el coste de cada integración. En Claude Code, los agentes de plugin pueden aparecer con el prefijo `methodology:`.

## Autonomía y permisos

La metodología no pide permiso para ramas, commits, integraciones ni versiones. El plugin **no** cambia el modo de permisos de Claude Code: eso se decide en cada repositorio. Para que no haya confirmaciones, configura `.claude/settings.json` del repo (por ejemplo, `defaultMode: acceptEdits` y reglas `allow` para `Bash(git:*)`, `Bash(gh:*)` y `Bash(python3:*)`; verifica la sintaxis en la [documentación de permisos](https://docs.claude.com/en/docs/claude-code/iam)) o ejecuta Claude dentro de un sandbox o devcontainer.

Si un repositorio necesita supervisión, añade un hook en ese repositorio (por ejemplo, uno `PreToolUse` que pida confirmación para `mth release`).

## Límites conocidos

- **El guard no es una frontera de seguridad.** Analiza el texto del comando; un comando ofuscado lo evade. La imposición real sobre `main` y `development` es el ruleset de GitHub. Si el guard falla, deja pasar (fail-open documentado) para no paralizar al agente.
- **Rulesets:** requieren permisos de administración y, en repositorios privados, un plan de GitHub que los incluya. Si no se pueden aplicar, `mth init --github` avisa y el flujo local sigue imponiendo las mismas reglas.
- **Las revisiones se registran en `.git/mth/`** (local): no viajan entre máquinas. Su resumen queda en la descripción del PR.
- **No se puede verificar automáticamente** que un commit sea temático, que esté en inglés ni que una docstring sea suficiente: es criterio de quien desarrolla y de los revisores.
- **Hook `commit-msg`:** script `sh`; no probado en Windows nativo.
- **Perfil de lenguaje:** las reglas de código son genéricas. Los perfiles por lenguaje se añadirán como referencias de las skills cuando haya un segundo proyecto que los justifique.

## Desarrollo del plugin

```
python -m unittest discover -s tests -v
```

El test de extremo a extremo recorre adopción → feature con rama hija → revisión → CI en rojo y reanudación → release interrumpida y reanudada → hotfix, contra un remoto local y un `gh` simulado que produce merge commits reales.
