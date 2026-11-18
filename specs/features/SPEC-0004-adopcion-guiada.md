# SPEC-0004 · Adopción guiada

- Estado: implementada
- Fecha: 2026-11-18
- ADRs: ADR-0003
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0004/AC-NN`. -->

## Contexto

`mth init` adopta la metodología añadiendo ficheros, sin mirar cómo trabaja ya el repo. En un repo avanzado eso provoca conflictos silenciosos: specs que dejan de estar trazadas, un hook `commit-msg` ajeno que desactiva la validación, agentes del repo que sustituyen a los del plugin, o instrucciones de CLAUDE.md que contradicen las reglas base. Además, el plugin aplica sus reglas antes de que nadie decida adoptarlo. [ADR-0003](../adr/process/ADR-0003-adopcion-guiada-por-perfiles-de-destino.md) recoge la decisión.

## Objetivo

1. El plugin no actúa en un repo que no lo ha adoptado, salvo para proponer la adopción.
2. Un inventario determinista clasifica el repo y decide qué preguntas hacen falta.
3. Una entrevista conducida por Opus presenta la metodología, pregunta solo lo necesario y produce un JSON de respuestas.
4. `mth init --answers` convierte esas respuestas en configuración y en el ADR de adopción del repo, en la rama de adopción.

## Fuera de alcance

- Modelos de ramas sin `development` (trunk-based) y publicar con una herramienta externa. Las preguntas de ramas y versiones no los ofrecen.
- Convertir documentos, editar CLAUDE.md, renombrar agentes o crear workflows de CI de forma automática: lo hace Opus en la rama de adopción, siguiendo la skill.
- Gestores de hooks que regeneran sus ficheros (husky, lefthook, pre-commit). El inventario los detecta y la skill indica cómo añadir `mth check-msg`.
- Traducir los mensajes de `mth`.

## Comportamiento

### Antes de adoptar

Un repo git sin `.claude/methodology.toml`:

- **Hook de sesión.** No inyecta las reglas base. Inyecta un aviso fijo: el repo no ha adoptado la metodología, sus reglas no se aplican y, en la primera respuesta de la sesión, Claude debe proponer la adopción guiada (skill `mth-init`) antes de cualquier otra tarea. Si la persona la rechaza, Claude respeta la forma de trabajar del repo.
- **Guard.** No bloquea ningún comando.
- **`mth init --decline`.** Escribe `"enabledPlugins": {"methodology@claude-methodology": false}` en `.claude/settings.local.json`, conservando el resto del fichero. Es idempotente. Desde ese momento, Claude Code no carga el plugin en ese repo.

### Inventario: `mth survey [--json]`

Solo lee: no modifica nada. Funciona sin `methodology.toml`; si existe, falla con el aviso de que el repo ya está adoptado.

Señales que detecta:

| Señal | Cómo se detecta |
|---|---|
| `files` | Número de ficheros versionados (`git ls-files`), sin contar `README*`, `LICENSE*`, `.gitignore`, `.gitattributes` ni `.claude/settings*.json` |
| `branches` | Ramas del remoto entre `main`, `master`, `development`, `develop`, `dev` |
| `upstream` | Existe el remoto `upstream` |
| `tags` | Etiquetas `<prefijo>X.Y.Z` y su prefijo más frecuente |
| `specs` | Carpetas `specs/`, `spec/`, `rfcs/`, `rfc/`, `design/`, `docs/specs/`, `docs/rfcs/`, `docs/design/` con ficheros `.md`, y el patrón de ID más frecuente de sus encabezados (`[A-Z]+-\d+`) |
| `adrs` | Carpetas `adr/`, `adrs/`, `decisions/`, `docs/adr/`, `docs/adrs/`, `docs/decisions/`, `doc/adr/`, `specs/adr/` con ficheros `.md`, y su patrón de ID. Sus ficheros no cuentan como specs |
| `agents` | Ficheros `.claude/agents/*.md`, y los que tienen el nombre de un agente del plugin (`verificador`, `documentador`) |
| `claude_dirs` | `.claude/skills/` o `.claude/commands/` con contenido |
| `instructions` | `CLAUDE.md`, `.claude/CLAUDE.md` o `AGENTS.md` no vacíos |
| `commit_hook` | Un `commit-msg` ajeno en el directorio de hooks de git |
| `hook_managers` | `.husky/`, `lefthook.yml`, `.pre-commit-config.yaml`, `commitlint.config.*`, `.commitlintrc*` |
| `release_tools` | `release-please-config.json`, `.changeset/`, `.releaserc*`, `CHANGELOG.md` sin el marcador de `mth` |
| `version_files` | `package.json`, `pyproject.toml`, `Cargo.toml` con un campo de versión `X.Y.Z` |
| `ci` | Ficheros en `.github/workflows/` |
| `tests` | Candidatos a comando de tests: script `test` de `package.json`, `pytest` si hay configuración de pytest o ficheros `test_*.py`, objetivo `test:` del `Makefile`, `go test ./...` con `go.mod`, `cargo test` con `Cargo.toml` |
| `language` | `es`, `en` o `unknown`, según las palabras vacías de `README.md` y `docs/**/*.md` (hasta 64 KiB). Con menos de 40 palabras reconocidas, `unknown` |

**Perfil**, en este orden:

1. `fork`, si existe `upstream`.
2. `methodology`, si hay alguna señal de proceso: `specs`, `adrs`, `agents`, `claude_dirs`, `instructions`, `commit_hook`, `hook_managers` o `release_tools`.
3. `new`, si `files` es 0.
4. `existing`, en cualquier otro caso.

**Preguntas.** Cada pregunta tiene un ID fijo. Se hacen las de la base del perfil más las que dispara una señal:

| ID | Base de los perfiles | Se dispara además si |
|---|---|---|
| `alcance` | existing, methodology, fork | — |
| `ramas` | — | no existe `development` en el remoto (en un repo nuevo, `development` se crea sin preguntar) |
| `commits` | — | `commit_hook` o `hook_managers` |
| `versiones` | fork | `tags`, `release_tools` o `version_files` |
| `specs` | — | `specs` |
| `decisiones` | — | `adrs` |
| `tests` | — | hay ficheros versionados y los candidatos no son exactamente uno |
| `revisores` | — | `agents` |
| `colision` | — | algún agente tiene el nombre de uno del plugin |
| `instrucciones` | — | `instructions` |
| `autonomia` | todos | — |
| `idioma` | new | `language` no es `es` |
| `ci` | — | no hay `ci` |
| `modelos` | todos | — |

Un repo nuevo hace como mucho cuatro preguntas (`autonomia`, `idioma`, `ci`, `modelos`).

`mth survey` muestra el perfil, las señales encontradas y las preguntas. Con `--json` escribe un objeto `{"profile", "signals", "questions"}`, en el que cada pregunta lleva su ID y la evidencia que la dispara.

### Entrevista: skill `mth-init`

- Frontmatter con `model: opus`.
- Un catálogo, `skills/mth-init/preguntas.md`, con una sección por ID. Cada sección tiene el texto fijo de la pregunta (qué hace la metodología y por qué, la evidencia del repo y la pregunta), las opciones (etiqueta, descripción con la consecuencia y vista previa) y la respuesta JSON que produce cada opción.
- El flujo de la skill: un mensaje de apertura que presenta la metodología y el inventario; las preguntas con `AskUserQuestion`, en rondas de hasta cuatro; en el perfil `methodology`, un plan de migración por artefacto que la persona aprueba o ajusta (hasta tres rondas de ajuste, y después se detiene y avisa); y un mensaje de cierre con lo aplicado tal cual, lo adaptado y el ADR que lo registra.
- Sin sesión interactiva: con el perfil `new`, adopta con los valores por defecto; con cualquier otro, muestra el inventario y se detiene.

### Respuestas: `mth init --answers FICHERO`

JSON `{"answers": {"<id>": {"option": "<opción>", ...}}}`. Opciones y efecto:

| ID | Opciones (parámetros) | Efecto en la configuración |
|---|---|---|
| `alcance` | `gradual`, `completa` | `gradual`: `trace.legacy_base` = commit de partida de la adopción ([SPEC-0005](SPEC-0005-modo-legado-en-la-trazabilidad.md)) |
| `ramas` | `usar` (`branch`), `crear` | `branches.development` |
| `commits` | `sustituir`, `encadenar` | `hooks.commit_msg` = `replace` / `chain` ([SPEC-0006](SPEC-0006-hooks-commit-msg-encadenados.md)) |
| `versiones` | `continuar`, `prefijo` (`tag_prefix`); en ambas, `version_files` opcional | `release.tag_prefix` (el detectado con `continuar`) y `release.version_files` |
| `specs`, `decisiones` | `mapear` (`path`, `kind`, `pattern`), `convertir`, `archivar` | `mapear`: `paths.specs` o `paths.adr`, `ids.<kind>` y `trace.spec_kind` o `trace.adr_kind` |
| `tests` | `comando` (`command`), `ninguno` | `commands.test` |
| `revisores` | `agentes` (`agents`: lista) | `review.agents` = `verificador` y la lista, en ese orden |
| `colision` | `renombrar` (`renames`: {viejo: nuevo}), `mantener` | `review.agents` y `roles` con los nombres nuevos |
| `instrucciones` | `metodologia`, `repo` (`exceptions`: lista de textos) | Ninguno; solo el ADR |
| `autonomia` | `full`, `until-pr`, `supervised` | `autonomy.level` ([SPEC-0007](SPEC-0007-autonomia-configurable.md)) |
| `idioma` | `es`, `en` | `language.docs` ([SPEC-0008](SPEC-0008-idioma-de-la-documentacion-configurable.md)) |
| `ci` | `sin-ci`, `crear` | `ci.required` = `false` / `true` |
| `modelos` | `equilibrado`, `calidad`, `ahorro` | `models.ladder`, `models.review` |

Lo que no se pregunta toma el valor que indica el inventario: `commands.test` es el único candidato si hay exactamente uno, `ci.required` es `true` si hay workflows, y `branches.main` es la rama principal del remoto. Con el perfil `fork`, además, `paths.claude_md = ".claude/CLAUDE.md"` y `commits.external_refs` con la rama principal de `upstream`.

Cualquier pregunta admite además `{"option": "otro", "config": {...}, "note": "..."}`. `config` son claves de `methodology.toml` que se fusionan con el resultado, y `note` es el texto de la persona, que se copia al ADR.

`mth init --answers`:

1. Repite el inventario y exige una respuesta válida para cada pregunta que el inventario pida. No admite respuestas a preguntas que no pide.
2. Genera la configuración: la plantilla, más los efectos de cada respuesta, más las claves `config` de las respuestas `otro`. La valida antes de tocar nada.
3. Hace lo mismo que `mth init`: crea la rama de adopción, escribe los ficheros e instala el hook según `hooks.commit_msg`.
4. Escribe en la rama un ADR de adopción, `Adopción de claude-methodology`, en `<carpeta de ADR>/methodology/` y en el idioma de `language.docs`: el perfil, una tabla con cada pregunta, la opción elegida y su efecto, y las notas de las respuestas `otro` y de `instrucciones`.
5. Hace un único commit `chore(methodology): adopt claude-methodology` y sube la rama. Opus completa después en la misma rama lo que no es determinista.

`mth init` sin `--answers` sigue funcionando como hasta ahora (plantilla con valores por defecto).

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Hook de sesión o guard sin configuración | `session`, `guard` | El aviso de adopción y ningún bloqueo; un fallo del hook sigue sin bloquear la sesión |
| `settings.local.json` ilegible | `mth init --decline` | Error que nombra el fichero; no se sobrescribe |
| `mth survey` en un repo ya adoptado | `mth survey` | Error: el repo ya está adoptado; usa `mth doctor` |
| Fichero ilegible o enorme durante el inventario | `mth survey` | Se ignora la señal de ese fichero y se avisa; el resto del inventario sigue |
| JSON de respuestas inválido, con preguntas sin responder, preguntas que el inventario no pide, opciones o parámetros desconocidos | `mth init --answers` | Error con la pregunta y el motivo; no se modifica nada |
| Configuración resultante inválida (también por las claves de `otro`) | `mth init --answers` | Error de validación de la configuración; no se modifica nada |
| Árbol sucio, sin remoto `main` o rama de adopción ya existente | `mth init --answers` | Los mismos errores que `mth init` |
| La persona no aprueba el plan de migración tras tres rondas de ajuste | Skill `mth-init` | Se detiene y avisa con lo pendiente; no adopta |

## Criterios de aceptación

- **AC-01**: Sin `methodology.toml`, el hook de sesión imprime el aviso de adopción y no las reglas base; con él, imprime las reglas base.
- **AC-02**: Sin `methodology.toml`, el guard no bloquea comandos que sí bloquea en un repo adoptado (push a `main`, rebase).
- **AC-03**: `mth init --decline` desactiva el plugin en `.claude/settings.local.json` conservando las demás claves, es idempotente y falla sin sobrescribir si el fichero no es JSON válido.
- **AC-04**: `mth survey --json` clasifica como `new` un repo con solo README, como `existing` uno con código y sin señales de proceso, como `methodology` uno con specs, agentes o un hook ajeno, y como `fork` uno con remoto `upstream`.
- **AC-05**: Las preguntas del inventario son las de la base del perfil más las disparadas por cada señal de la tabla; un repo nuevo produce como mucho `autonomia`, `idioma`, `ci` y `modelos`.
- **AC-06**: El inventario detecta specs y ADR con su patrón de ID, agentes y colisiones de nombre, gestores de hooks, herramientas de publicación, ficheros de versión, candidatos a comando de tests e idioma, y no modifica el repo.
- **AC-07**: `mth survey` falla en un repo adoptado, y un fichero ilegible durante el inventario produce un aviso sin detener el resto.
- **AC-08**: `mth init --answers` rechaza, sin modificar nada, un JSON inválido, una pregunta pedida sin responder, una pregunta no pedida, una opción o un parámetro desconocidos y unas claves `otro` que dejan la configuración inválida.
- **AC-09**: `mth init --answers` genera la configuración con el efecto de cada opción de la tabla, los valores del inventario para lo que no se pregunta, los ajustes del perfil `fork` y las claves de `otro` fusionadas.
- **AC-10**: `mth init --answers` crea la rama de adopción con un único commit que incluye la configuración y el ADR de adopción, con el perfil, cada pregunta, su opción y las notas.
- **AC-11**: El catálogo de la skill tiene una sección por cada ID de pregunta del inventario, con opciones que coinciden con las que acepta `mth init --answers`, y la skill declara `model: opus`.

## Notas

Las capacidades que ofrecen algunas opciones tienen su propia spec: modo legado ([SPEC-0005](SPEC-0005-modo-legado-en-la-trazabilidad.md)), hooks encadenados ([SPEC-0006](SPEC-0006-hooks-commit-msg-encadenados.md)), autonomía configurable ([SPEC-0007](SPEC-0007-autonomia-configurable.md)) e idioma configurable ([SPEC-0008](SPEC-0008-idioma-de-la-documentacion-configurable.md)). Se implementan en ramas hijas de esta feature.
