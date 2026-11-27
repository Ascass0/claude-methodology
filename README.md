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
│   ├── skills/mth-*/SKILL.md         # develop, plan, init, spec, branch, commit, review, integrate, release, trace
│   ├── agents/                       # agentes compartidos: verificador, documentador, planificador
│   ├── catalog/                      # plantillas de agentes instalables (no activas)
│   └── templates/                    # config, spec, ADR, CHANGELOG, bloque de CLAUDE.md
└── tests/                            # tests unitarios y de extremo a extremo (gh simulado)
```

## Requisitos

- Python ≥ 3.11 instalado (no hace falta que sea el `python3` activo: el lanzador `scripts/mth` busca uno válido aunque pyenv o un venv apunten a otra versión; `MTH_PYTHON` lo fija), git y [GitHub CLI](https://cli.github.com/) autenticado (`gh auth login`).
- Un repositorio con `main` y al menos un commit. El flujo completo (PR, CI, merges y releases) necesita GitHub; en GitLab o sin forja, `mth` hace la parte local y te dice los pasos manuales (ver «Forja»).

## Instalación

1. En Claude Code: `/plugin marketplace add Ascass0/claude-methodology` y `/plugin install methodology@claude-methodology`. El repositorio es público: no hace falta ninguna credencial. Abre una sesión nueva después de instalar.
2. En cada repositorio, la skill `mth-init` (o `mth init --marketplace-repo Ascass0/claude-methodology --github`) deja la activación del plugin en su `.claude/settings.json`, de modo que cualquier clon lo carga.

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

1. `mth survey` inventaria el repo sin modificarlo (ramas, specs y ADR existentes, agentes, hooks, herramientas de release, CI, forja del remoto) y resuelve cada pregunta como `deducida` (la resuelve una señal, con su evidencia), `por_defecto` o `decision` ([SPEC-0015](specs/features/SPEC-0015-adopcion-deducir-por-defecto-o-preguntar.md), [ADR-0011](specs/adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md)).
2. Opus presenta la metodología y pregunta, empezando por la precedencia entre el repo y la metodología, solo las `decision`, en una ronda (un repo nuevo hace como mucho seis; más de cuatro van en dos rondas). Solo ofrece las opciones que funcionan con el repo: por ejemplo, un hook `commit-msg` ajeno solo se encadena, y sin GitHub no se ofrece `ci: crear`.
3. `mth init --answers <json> --plan` muestra, sin escribir nada, lo deducido, lo que va por defecto, lo decidido y las capacidades activas y desactivadas con su motivo. Con la confirmación de la persona, `mth init --answers <json>` convierte las respuestas en `.claude/methodology.toml` y en el ADR de adopción, que registra el resultado de cada pregunta.
4. Si no se quiere adoptar, `mth init --decline` desactiva el plugin en ese repo (`.claude/settings.local.json`, no versionado).

`mth init` sin `--answers` sigue existiendo y adopta con la plantilla por defecto:

- crea `development` desde `main` si no existe;
- abre `chore/adopt-methodology` con `.claude/methodology.toml`, `docs/`, `specs/features/`, `specs/adr/`, `changes/`, `CHANGELOG.md` (con marcador de versiones) y un bloque gestionado en `CLAUDE.md` (el resto del fichero no se toca);
- instala el hook `commit-msg` (según `hooks.commit_msg` si ya había uno);
- con `--github`: solo merge commits en el repo y un ruleset que protege `main` y `development` (PR obligatorio, sin borrado ni force-push).

Después se ajusta `.claude/methodology.toml` (comando de tests, esquema de IDs, revisores, roles, prefijos de rama propios), se comprueba con `mth doctor` y se integra con `mth integrate`. En una adopción gradual, `trace.legacy_base` evita que el contenido anterior bloquee la trazabilidad; `mth trace --legacy` lo lista.

### Decisión de versión

Si un cambio merece versión, y de qué nivel, lo decide `mth` en código ([SPEC-0017](specs/features/SPEC-0017-decision-autonoma-de-version.md), [ADR-0013](specs/adr/process/ADR-0013-decision-autonoma-de-version.md)). Tras integrar en `development`, `mth release --plan` (solo lee) imprime los fragmentos con su nivel, la versión propuesta y una decisión con sus motivos: `publicar`, `esperar` (hay ramas abiertas con fragmento), `no publicar` (sin fragmentos: el mantenimiento no versiona) o `bloqueado`. El nivel sigue SemVer: el mayor entre los fragmentos, con un mínimo por fragmento que se comprueba al integrar y al publicar (`feat` → `minor`; `fix`, `hotfix` y `security` → `patch`; eliminar funcionalidad → `minor` en `0.y.z` y `major` desde `1.0.0`). `1.0.0` declara la API estable: solo se publica con `mth release --allow-major`, decisión de la persona. Con `autonomy.level = full`, el agente publica cuando la decisión es `publicar`.

### Forja

`forge` (`github`, `gitlab` o `none`) se deduce de la URL del remoto: `github.com` es `github`; `gitlab.com` o un host cuya primera etiqueta es `gitlab`, `gitlab`; el resto, `none`. Con `github` todo funciona como se describe aquí. Con `gitlab` o `none`, `mth` nunca fusiona, porque no puede comprobar la CI:

- `mth integrate` supera los gates locales, sube la rama, deja el título y la descripción del MR en `.work/merge-request/` y lista los pasos manuales (abrir el MR, esperar a la CI, fusionar con merge commit y volver a ejecutar `mth integrate`, que detecta el merge y limpia).
- `mth release` calcula la versión, genera el `CHANGELOG.md`, prepara y sube `release/vX.Y.Z` y lista los pasos manuales (MR a `main`, etiqueta, release y MR de vuelta a `development`), marcando los que git confirma al repetirlo.
- `mth hotfix finish` no está soportado; `mth doctor` no pide `gh` ni CI; el guard bloquea `glab mr merge` igual que `gh pr merge`.

El soporte completo de GitLab (`glab`, estado de los pipelines, releases) queda fuera: se abrirá un ADR propio cuando haya demanda.

### Reestructurar la metodología

En un repo ya adoptado, la skill `mth-reconfigure` vuelve a pasar la entrevista de la adopción: el formulario completo, los bloques que se elijan (`flujo`, `documentacion`, `calidad`, `agente`) o solo el cambio que se describa ([SPEC-0011](specs/features/SPEC-0011-reestructuracion-guiada-de-la-metodologia.md), [ADR-0007](specs/adr/process/ADR-0007-reestructuracion-reutilizando-la-entrevista-de-adopcion.md)).

Cuando el plugin se actualiza, la skill `mth-update` (que solo lanza la persona) pone el repo al día: `mth update --plan` lista las brechas (configuración, agentes del catálogo, bloque de CLAUDE.md, hook, formato de specs y ADR), `mth update` aplica las deterministas en `chore/update-methodology` sin cambiar ninguna decisión ya tomada, y la skill conduce lo que exige criterio ([SPEC-0021](specs/features/SPEC-0021-actualizacion-del-repo-adoptado-al-plugin-nuevo.md), [ADR-0017](specs/adr/process/ADR-0017-actualizacion-de-un-repo-adoptado-por-brechas-deterministas.md)).

1. `mth survey --reconfigure [--only <bloques o preguntas>]` ofrece las preguntas aplicables con su valor actual (solo lee).
2. Opus pregunta con los textos del catálogo de `mth-init`, marcando la opción actual.
3. `mth reconfigure --answers <json> [--only …]` valida las respuestas y las aplica **sobre la configuración actual**, así que lo que no se pregunta se conserva. Abre `chore/reconfigure-methodology` con la configuración y un ADR de reestructuración en un único commit, que cita el ADR de adopción y lista cada clave que cambia. Si nada cambia, no crea nada.
4. Las migraciones que pidan las respuestas (convertir specs, renombrar agentes, crear la CI) se hacen en la misma rama, tras aprobar el plan, y se integra con `mth integrate`.

El fichero de configuración se regenera, así que se pierden sus comentarios: el porqué de cada cambio queda en el ADR.

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
| `roles.*` | Agentes del repo para coder, documentador, verificador y planificador (`roles.planner`, por defecto `planificador`) |
| `plans.required_for` | Tipos de rama que necesitan un plan acordado antes de crearse y de integrarse (por defecto `feat`, `fix` y `hotfix`). El plan es un fichero local de `.work/plans/`, nunca se commitea. Ver [SPEC-0023](specs/features/SPEC-0023-planes-acordados-antes-de-desarrollar.md) y [ADR-0021](specs/adr/process/ADR-0021-planes-acordados-antes-de-desarrollar.md) |
| `models.*` | Escalera de reintento (`ladder`, por defecto `haiku`, `sonnet`, `opus`) y nivel de las tareas sin modelo (`task`), de los revisores (`review`) y del documentador (`documenter`). Ver [SPEC-0002](specs/features/SPEC-0002-niveles-de-modelo.md); `mth models` los muestra y, además, indica que el planificador va fijo en `opus` (no es configurable) |
| `ci.required` | Exigir CI en verde en cada PR (fail-safe) |
| `trace.*` | Comprobaciones activas, ficheros incluidos (`include`) y exclusiones justificadas |
| `trace.legacy_base` | Commit de la adopción gradual: los hallazgos en ficheros sin cambios desde él son avisos y `mth trace --legacy` los lista. Ver [SPEC-0005](specs/features/SPEC-0005-modo-legado-en-la-trazabilidad.md) |
| `hooks.commit_msg` | Qué hacer con un hook `commit-msg` ajeno: `own` (lo deja), `replace` (instala el de mth) o `chain` (lo ejecuta antes de validar). Ver [SPEC-0006](specs/features/SPEC-0006-hooks-commit-msg-encadenados.md) |
| `hooks.pre_commit` | Igual que `hooks.commit_msg`, para el hook `pre-commit` de secretos: `own` (por defecto, deja el ajeno), `replace` (lo guarda como `pre-commit.pre-mth`) o `chain` (lo guarda como `pre-commit.local` y lo ejecuta primero). No confundir con `commands.precommit`. Ver [SPEC-0024](specs/features/SPEC-0024-hook-de-precommit-y-workflow-de-ci-para-secretos.md) |
| `secrets.mode` / `hook` / `ci` | Gate al integrar (`mode`), hook `pre-commit` (`hook`) y workflow de CI (`ci`). Valores: `""` (sin decidir, por defecto), `"off"` y `"on"` (`mode` usa `"block"` en lugar de `"on"`). Ver [Secretos](#secretos-antes-del-commit-y-en-la-ci) |
| `autonomy.level` | `full` (por defecto), `until-pr` (integrar y publicar piden confirmación) o `supervised` (además, ramas, commits y push). Ver [SPEC-0007](specs/features/SPEC-0007-autonomia-configurable.md) y [ADR-0004](specs/adr/process/ADR-0004-autonomia-configurable-por-repositorio.md) |
| `language.docs` | Idioma de docs, specs, ADR, changelog y PR: `es` (por defecto) o `en`. Código y commits, siempre en inglés. Ver [SPEC-0008](specs/features/SPEC-0008-idioma-de-la-documentacion-configurable.md) |
| `forge` | Forja del remoto: `github` (por defecto), `gitlab` o `none`. Se deduce del remoto al adoptar. Ver [SPEC-0016](specs/features/SPEC-0016-forja-configurable.md) y [ADR-0012](specs/adr/process/ADR-0012-forja-configurable.md) |
| `release.*` | Release de GitHub, firma y prefijo de las etiquetas (`tag_prefix`) y ficheros que declaran la versión (`version_files`: `path` y `pattern` con un grupo de captura), que `release` y `hotfix finish` actualizan en el commit de la versión y `doctor` verifica. Ver [SPEC-0003](specs/features/SPEC-0003-ficheros-de-version-en-la-publicacion.md) |
| `[agents.<agente>]` | Variables de un agente del catálogo (`bench`, `databases`…). Opcional; solo admite las claves que declara ese agente. Requiere plugin ≥ 0.8.0 (un plugin anterior la rechaza, ver [SPEC-0009](specs/features/SPEC-0009-actualizacion-del-plugin-con-configuracion-mas-nueva.md)) |
| `work.dirs` | Subdirectorios propios del repo en `.work/`, además de los de serie. Ver [Directorio de trabajo local](#directorio-de-trabajo-local) |

### Secretos antes del commit y en la CI

Además del gate de `mth integrate` ([ADR-0020](specs/adr/security/ADR-0020-gate-de-secretos-en-el-historial.md)), hay dos piezas opcionales ([SPEC-0024](specs/features/SPEC-0024-hook-de-precommit-y-workflow-de-ci-para-secretos.md), [ADR-0022](specs/adr/security/ADR-0022-hook-de-precommit-y-workflow-de-ci-para-secretos.md)). Ninguna se activa sola: nacen sin decidir y la decisión se toma en la adopción (pregunta `secretos`: `bloquear`, `integrar` o `ninguno`) o con `mth update`.

- **`mth secrets --staged`:** escanea con `gitleaks` solo lo preparado y nunca imprime valores. Falla cerrado: sin `gitleaks`, con un error de la herramienta o al agotar el tiempo, termina con error. Requiere `gitleaks` 8.19.0 o posterior, en el `PATH` o instalado con `mth tools install gitleaks` (ver [Herramientas externas](#herramientas-externas-mth-tools)); `mth doctor` informa del origen y la versión, y avisa de una versión anterior o de una copia gestionada de otra versión que la del manifiesto.
- **Hook `pre-commit`** (`secrets.hook = "on"`): ejecuta `mth secrets --staged` y rechaza el commit si hay secretos o si no encuentra `mth`. Convive con un hook ajeno según `hooks.pre_commit`; con el directorio de hooks versionado, `replace` y `chain` fallan sin tocar nada y piden añadir `mth secrets --staged` al gestor de hooks. `git commit --no-verify` lo salta: por eso existe la CI. Con `"off"`, `mth` retira su hook y no toca uno ajeno.
- **Workflow `.github/workflows/secrets.yml`** (`secrets.ci = "on"`): solo con `forge = github` y `ci.required = true`. Escanea cada PR y cada push a `main` y `development` con un binario de `gitleaks` de versión y suma de comprobación fijadas, sin acciones de terceros para escanear. Lo escribe `mth` desde la plantilla, con `secrets.baseline` sustituida (solo letras, cifras, `.`, `_`, `-` y `/`). Lleva una marca en la primera línea: un fichero con ese nombre sin marca es ajeno y no se sobrescribe; `mth doctor` avisa.
- **Protección de rama:** una rama puede editar o borrar el workflow en su propio PR. La protección de `main` y `development` debe exigir la comprobación del workflow, y la revisión debe mirar los cambios de `.github/workflows/**`.
- **Brechas de `mth update`:** `secretos-hook` y `secretos-ci` (decisión, mientras la clave está sin decidir) y `secretos-workflow` (automática: escribe el workflow cuando falta o está desactualizado, una vez decidido). Con el hook activado, `mth update` también lo reinstala si falta.

### Herramientas externas (`mth tools`)

Los gates dependen de herramientas externas (hoy `gitleaks`). `mth` no las empaqueta ni las descarga por su cuenta: la descarga solo ocurre con una orden explícita. Ver [SPEC-0025](specs/features/SPEC-0025-gestor-de-herramientas-externas.md) y [ADR-0023](specs/adr/security/ADR-0023-gestor-de-herramientas-externas.md).

| Orden | Hace |
|---|---|
| `mth tools` | Lista cada herramienta con la versión del manifiesto, su origen (`PATH`, `gestionada` o `ausente`) y la versión encontrada. No usa la red |
| `mth tools install <herramienta> [--force]` | Descarga, verifica y publica la copia gestionada de la versión del manifiesto. Si ya está instalada y es válida, no descarga; `--force` la reinstala |
| `mth tools prune` | Borra las versiones gestionadas que ya no están en el manifiesto y las instalaciones a medias. No borra nada sin esta orden |

**Orden de resolución.** Si la herramienta está en el `PATH` y alcanza la versión mínima que pide quien la usa, se usa esa. Si es anterior o su versión no se reconoce, se prefiere la copia gestionada válida; sin ella se usa la del `PATH` y se avisa. Sin `PATH`, se usa la copia gestionada. Sin ninguna, error con `mth tools install <herramienta>`: resolver nunca descarga.

**Caché.** `<caché>/claude-methodology/tools/<herramienta>/<versión>/`, donde `<caché>` es `MTH_TOOLS_DIR` si está definida y, si no, el directorio de caché del sistema (`XDG_CACHE_HOME` o `~/.cache` en Linux, `~/Library/Caches` en macOS, `%LOCALAPPDATA%` en Windows). Se puede borrar y regenerar. Los directorios se crean con permisos solo del usuario.

**Verificación.** La URL debe ser https. La suma SHA-256 del archivo se comprueba antes de extraer; la extracción rechaza rutas absolutas o con `..`, enlaces y ficheros especiales, y acota tamaño y número de miembros. La copia se publica con un renombrado atómico y la suma del ejecutable se comprueba antes de cada uso: si no coincide, `mth` falla sin ejecutarlo y pide `mth tools install <herramienta> --force`.

**Límite.** No hay verificación de firmas: la suma del manifiesto comparte origen con el binario, así que protege de descargas dañadas o alteradas en tránsito, no de una release comprometida.

**Plataformas de `gitleaks`:** linux x64 y arm64, darwin x64 y arm64, y windows x64. Los formatos admitidos son `tar.gz` y `zip`. Windows y `.zip` no se han probado con binarios reales, solo con archivos generados en los tests.

**Añadir o actualizar una herramienta.** Se edita `plugins/methodology/tools/manifest.toml`, sin código nuevo:

- Una sola versión por herramienta, con `version_args` (argumentos que imprimen su versión) y una entrada `platforms.<sistema>_<arquitectura>` con `url`, `sha256`, `format` y `entry`.
- Las sumas se copian de la release oficial, no se calculan de una descarga propia.
- El PR lo revisa `revisor-seguridad`.
- Para `gitleaks`, la versión y la suma de `linux_x64` deben coincidir con las de la plantilla del workflow de CI de secretos (`plugins/methodology/templates/workflows/`).

### Auditoría de hardening (`mth audit`)

El agente opcional `auditor-estatico` audita un dominio del repo (`docker`, `kubernetes` o la matriz `comun`) contra un **pack de línea base**: un fichero TOML versionado en `plugins/methodology/audit/packs/` con controles de fuente verificada, título propio y fecha de revisión. `mth audit packs` los lista (versión, hash y si están vigentes; `mth doctor` avisa de los caducados) y `mth audit verify <informe>` valida el informe: solo controles que el pack define, un resultado (`cumple`, `no cumple`, `no evaluable`) con evidencia para cada control mínimo, la versión y el hash del pack, y nunca «certificado». Sin la herramienta (p. ej. `hadolint`), el control queda `no evaluable`; la auditoría no certifica el cumplimiento de ninguna norma. El agente `auditor-ejecucion` audita TLS y SSH de servicios en marcha (packs `tls` y `ssh`) y solo escanea los destinos que la persona autoriza en `audit.targets` (`.claude/methodology.toml`, vacía por defecto); su única vía de red es `mth audit scan <testssl|ssh-audit> <destino>`, que rechaza todo destino que no coincida exactamente con una entrada, y las herramientas las instala quien audita ([SPEC-0028](specs/features/SPEC-0028-auditor-de-ejecucion-con-destinos-autorizados.md), [ADR-0025](specs/adr/security/ADR-0025-destinos-de-escaneo-autorizados-por-configuracion.md)). Flujo en la skill `mth-audit`; diseño en [SPEC-0027](specs/features/SPEC-0027-auditor-estatico-y-packs-de-linea-base.md) y [ADR-0024](specs/adr/security/ADR-0024-packs-de-linea-base-en-toml-y-verificacion-del-informe.md).

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
| Toda idea `feat`, `fix` o `hotfix` parte de un plan acordado con la persona, antes de la rama | `mth plan new/agree/list/show/done`; `mth branch --plan PLAN-NNNN` exige el plan acordado y `mth integrate` y `mth hotfix finish` exigen que la rama figure en un plan en curso (`[plans]`). Ver [ADR-0021](specs/adr/process/ADR-0021-planes-acordados-antes-de-desarrollar.md) |
| Toda feature parte de una spec | `mth integrate` exige que el fragmento de una `feat` referencie su spec |
| Cada AC tiene test | `mth trace`: una spec `implementada` sin `verifies: SPEC/AC` falla |
| Una spec que declara superficie de seguridad (`- Seguridad:` distinta de `ninguna`) tiene al menos un AC `[SEG]` | `mth trace` (formato compacto). Ver [SPEC-0026](specs/features/SPEC-0026-criterios-de-seguridad-en-las-specs.md) |
| IDs únicos y referencias válidas | `mth trace` (también tras `mth sync`, donde aparecen las colisiones de ramas paralelas) |
| Enlaces internos válidos y dentro del repo | `mth trace` |
| Ningún fichero supera `limits.max_file_lines` sin excepción con techo y motivo; solo hacerlo crecer bloquea | `mth trace` (`[limits]`). Ver [ADR-0016](specs/adr/process/ADR-0016-limite-de-lineas-por-fichero.md) |
| Ningún secreto nuevo llega a `development`: `gitleaks` escanea la rama antes de subirla; los hallazgos viejos se aceptan de forma explícita y se rotan | `mth integrate` con `[secrets]` (`secrets.mode = "block"`) y `mth secrets [--history [--accept]]`; antes del commit, hook `pre-commit` (`secrets.hook`) y en la CI, workflow `secrets.yml` (`secrets.ci`). Ver [ADR-0020](specs/adr/security/ADR-0020-gate-de-secretos-en-el-historial.md) y [ADR-0022](specs/adr/security/ADR-0022-hook-de-precommit-y-workflow-de-ci-para-secretos.md) |
| Cada test lleva etiqueta (`verifies:`, `regression:` o `unit:`); aviso de los AC con un único test | `mth trace` (`trace.test_patterns`; en ficheros legados, aviso). Ver [ADR-0015](specs/adr/process/ADR-0015-triangulacion-y-motivo-declarado-de-cada-test.md) |
| Specs y ADR con `- Formato: compacto`: criterios en EARS, `FM-NN` únicos y referenciados, campos fijos del ADR | `mth trace` (los documentos sin la marca no se validan). Ver [ADR-0014](specs/adr/process/ADR-0014-formato-compacto-de-specs-y-adr.md) |
| Conventional Commits + cuerpo + `Refs:` | `mth commit`, hook `commit-msg`, revalidación en `mth integrate` |
| Modelo de ramas y ramas hijas | `mth branch` (nombres validados; hijas con `--`) |
| Hijas integradas antes que la padre | `mth integrate` |
| Merge commit, nunca squash ni rebase | `mth integrate` / `release` + guard + ajustes de GitHub |
| Sin reescritura de historia | Guard (force-push, rebase, `--no-verify`, borrado de tags) + ruleset |
| Revisión del HEAD final sin bloqueantes | `mth review record --report` calcula los bloqueantes contando los hallazgos del informe (por SHA) + `mth integrate` |
| Un revisor que no termina no cuenta como aprobado | `mth review record`: un informe ausente, vacío, de más de 256 KiB, ilegible o cuyo `BLOQUEANTES: <n>` no coincide con la cuenta de `mth` se registra como fallido, con su número de intento |
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
| Reestructuración trazada | `mth survey --reconfigure` + skill `mth-reconfigure` + `mth reconfigure --answers`: valida antes de tocar nada, conserva lo no preguntado y registra un ADR |
| Adopción sin conflictos silenciosos | `mth survey` + entrevista de `mth-init` + `mth init --answers`; sin adoptar, el plugin no actúa |
| Artefactos de trabajo fuera del repo | `.work/` excluido en `.git/info/exclude` por el hook de sesión y `mth init`; guard ante `git add` forzado; `mth doctor` |
| Cada agente del catálogo solo ejecuta lo que su guard permite | `mth agent-guard`: despacha por `agent_type` y falla cerrado |
| Un agente de solo lectura no escribe en la base de estado | `mth db-query`: `mode=ro`, `PRAGMA query_only` y authorizer |
| Trazabilidad de las operaciones | `.git/mth/trace.jsonl` (eventos JSON con ID de ejecución) |
| Diseño, excepciones, parsimonia, docs en código | Principios + revisores del repo (criterio) |

## Agentes

El plugin incluye tres agentes compartidos por todos los repos:

- **`verificador`**: primer revisor de cada rama. Comprueba que cada criterio y cada modo de fallo de la spec están implementados y cubiertos por un test que de verdad lo comprueba, ejecuta los tests, confirma que un fix trae su test de regresión y detecta afirmaciones falsas en commits, changelog y docs.
- **`documentador`**: actualiza docs, fragmento de changelog y los registros documentales que exija el repo, en español y sin duplicar fuentes de verdad.
- **`planificador`**: siempre con Opus y en solo lectura. Redacta el plan de una idea (tareas, agente sugerido de cada una, oleadas, dependencias y preguntas abiertas) y recomienda los agentes del catálogo que conviene instalar; no instala nada. Lo lanza la skill `mth-plan`; la persona acuerda el plan con `mth plan agree`. El orquestador (catálogo) instala los agentes recomendados y reparte el trabajo según el plan, y el verificador avisa si el diff se sale de él.

`mth plan new <slug>`, `agree PLAN-NNNN`, `list`, `show PLAN-NNNN` y `done PLAN-NNNN [--abandon]` gestionan los planes acordados, que viven en `.work/plans/PLAN-NNNN-<slug>.md` (local). `mth plan check|verify|model|stats` siguen operando sobre el plan de trabajo de la spec.

Cada repo añade en `.claude/agents/` sus **agentes de implementación** (`dev-*`), especializados por área, y sus revisores específicos. La sesión principal orquesta. Si delega dos o más tareas, el reparto es la sección `## Plan de trabajo` de la spec: tareas agrupadas en oleadas, con sus ficheros permitidos y sus criterios, que `mth plan check SPEC-NNNN` valida antes de lanzar nada. Las tareas de una oleada se ejecutan en paralelo; cada `dev-*` recibe un encargo autocontenido y devuelve un manifiesto JSON. Al cerrar la oleada, `mth plan verify SPEC-NNNN --wave N --manifest <fichero> …` contrasta los manifiestos con el plan y con los cambios reales del árbol de trabajo. Cada tarea lleva su modelo (columna `Modelo` del plan o `models.task`) y `mth plan model` da el alias que se pasa a la herramienta Agent. Una tarea no ejecutada o no completada se relanza una sola vez, con el nivel siguiente de la escalera (`mth plan model --retry`); si vuelve a fallar, la sesión principal la implementa o rehace el plan. Con `mth plan verify --model T-NN=alias` queda registrado qué modelo ejecutó cada tarea y `mth plan stats` resume los resultados por modelo. Los revisores y el documentador se lanzan con `models.review` y `models.documenter`. Los commits los hace siempre la sesión principal, al cerrar cada oleada. El formato del plan y del manifiesto está en [SPEC-0001](specs/features/SPEC-0001-delegacion-verificable.md) y la decisión, en [ADR-0001](specs/adr/process/ADR-0001-plan-y-manifiesto-verificados.md); los niveles de modelo, las métricas y su formato, en [SPEC-0002](specs/features/SPEC-0002-niveles-de-modelo.md) y [ADR-0002](specs/adr/process/ADR-0002-niveles-de-modelo.md); el protocolo, en la skill `mth-develop`.

Cada revisor termina su informe con la línea `BLOQUEANTES: <n>`. La sesión principal guarda el informe tal cual y lo registra con `mth review record <agente> --report <informe> --summary "…"`: `mth` archiva el informe literal en `.work/reviews/<sha>-<agente>-<n>.md`, cuenta él mismo los hallazgos `[bloqueante]` y contrasta la línea del agente. Una discrepancia o un formato ilegible dejan la revisión como fallida (con motivo e intentos), y se pide una única corrección al mismo agente con `SendMessage` ([SPEC-0013](specs/features/SPEC-0013-registro-de-revisiones-calculado-por-mth.md)).

Los revisores del repo se declaran en `review.agents` (en orden de precedencia). Con `[review.paths]`, un revisor de un área solo se exige cuando el diff la toca, lo que mantiene acotado el coste de cada integración. En Claude Code, los agentes de plugin pueden aparecer con el prefijo `methodology:`.

### Catálogo de agentes

Además de esos dos, el plugin trae un **catálogo** de 14 plantillas de agentes en `plugins/methodology/catalog/`, agrupadas en tres perfiles (`profiles.toml`): `base` (cinco revisores, `diagnosticador` y `explorador-specs`), `opcional` (`ingeniero-rendimiento`, `analista-evals`, `lector-estado`, `respondedor-incidencias`, `auditor-estatico`, `auditor-ejecucion`) y `autonomo` (`orquestador`). No están activas: cada repo instala las que quiere. Referencia operativa, tabla de agentes y prueba de humo en [docs/catalogo-de-agentes.md](docs/catalogo-de-agentes.md); diseño en [SPEC-0012](specs/features/SPEC-0012-catalogo-de-agentes.md) y [ADR-0008](specs/adr/process/ADR-0008-catalogo-de-plantillas-de-agentes.md).

- **Comandos:** `mth agents list|add|sync|diff|remove`. `add` acepta nombres o `--profile`. `mth smoke` comprueba con Claude Code real que el guard bloquea (abajo).
- **Renderizado determinista**, sin modelo de lenguaje: la misma configuración y las mismas variables (`[agents.<agente>]`) dan los mismos bytes. El agente queda en `.claude/agents/<agente>.md` con una cabecera de versión y hash. Su sección local (`<!-- mth:local:begin -->`…`end`) es del repo y `sync` la conserva; si se edita a mano la parte generada, `sync` se niega sin `--force`.
- **Revisores:** `add` los coloca en `review.agents` tras `verificador`, según el `review.order` de cada plantilla (los revisores propios del repo conservan su posición), y añade sus `paths` a `[review.paths]`.
- **Guard por agente:** `add` deja una entrada `PreToolUse` en `.claude/settings.json` y el shim `.claude/hooks/mth-agent-guard`. El shim despacha por `agent_type` y llama a `mth agent-guard`, que **falla cerrado**: sin reglas, sin lanzador o ante cualquier error, bloquea al subagente. El guard global sigue fallando abierto porque actúa sobre toda la sesión y las ramas compartidas las protege GitHub; un agente "de solo lectura" que escribe porque su guard se rompió es peor que un agente parado.
- **`lector-estado`** consulta bases SQLite declaradas con `mth db-query`, que no admite escrituras (ver la fila de la tabla anterior).
- **Adopción:** `mth init` ofrece el perfil `base` en la pregunta `revisores`, que ahora se hace siempre.
- **Modelo:** ninguna plantilla fija `model`. Los revisores usan `models.review` y los trabajadores `models.task`; `model_hint` solo se muestra en `mth agents list`.

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
- **El guard por agente no es una frontera de seguridad.** En los trabajadores con denylist, `python script.py` puede hacer cualquier cosa, también un `git push`, y las expansiones de shell (`g$'it' push`) no se analizan. Las fronteras reales son `isolation: worktree`, los rulesets de GitHub y, para `lector-estado`, `mth db-query`. En los agentes de allowlist (revisores, `lector-estado`, `respondedor-incidencias`), el guard rechaza programas con ruta, expansiones de shell sin comillas y filtros que escriben ([docs/catalogo-de-agentes.md](docs/catalogo-de-agentes.md)).
- **Depende de que Claude Code envíe `agent_id` y `agent_type`** en el payload del hook (verificado en Claude Code 2.1.330). Si dejara de enviarlos, el guard fallaría abierto sin aviso: `mth smoke` lo comprueba con un subagente canario ([SPEC-0014](specs/features/SPEC-0014-prueba-de-humo-de-los-agentes.md), [ADR-0010](specs/adr/process/ADR-0010-la-prueba-de-humo-exige-evidencia-independiente-del-guard.md)) y registra la versión de Claude Code que pasó; `mth session` y `mth doctor` avisan cuando cambia. Ejecútalo al actualizar Claude Code y antes de cada versión del plugin; el [procedimiento manual](docs/catalogo-de-agentes.md#prueba-de-humo) sigue disponible. Los hooks del frontmatter de los subagentes no se aplican en 2.1.330, por eso las plantillas no los usan.
- **Falsos positivos aceptados por fallar cerrado:** `deny_operators` busca subcadenas, así que `git grep ">"` se bloquea en los revisores; y `-F`, prohibido en `respondedor-incidencias` por `gh api`, también afecta a `git grep -F`.
- **Coste del guard por agente:** unos 3 ms por llamada de la sesión principal y unos 50 ms por llamada de un subagente del catálogo (medido en WSL).
- **Copias desactualizadas:** los agentes instalados solo se actualizan si alguien ejecuta `mth agents sync`; `mth doctor` avisa pero no bloquea.
- **`mth db-query` solo abre bases dentro del repositorio.** Un alias que apunte fuera (ruta absoluta, `..` o enlace) se rechaza.
- **SQLite en WAL:** `mode=ro` necesita poder crear o leer el fichero `-shm`.
- **Las plantillas del catálogo están en español.** Con `language.docs = "en"` se avisa y los agentes se instalan igualmente en español.
- **El `orquestador` (perfil `autonomo`) es experimental.**
- **Hook `commit-msg`:** script `sh`; no probado en Windows nativo.
- **Perfil de lenguaje:** las reglas de código son genéricas. Los perfiles por lenguaje se añadirán como referencias de las skills cuando haya un segundo proyecto que los justifique.

## Desarrollo del plugin

```
sh tests/run.sh -v
```

`tests/run.sh` ejecuta los tests con el primer Python ≥ 3.11 que encuentra (`MTH_PYTHON` lo fija).

El test de extremo a extremo recorre adopción → feature con rama hija → revisión → CI en rojo y reanudación → release interrumpida y reanudada → hotfix, contra un remoto local y un `gh` simulado que produce merge commits reales.

## Licencia

[MIT](LICENSE).
