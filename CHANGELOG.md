# Changelog

Todos los cambios relevantes de este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Los cambios pendientes de publicar viven como fragmentos en `changes/` y se incorporan aquí al publicar cada versión.

<!-- mth:releases -->

## [0.17.0] - 2026-11-27

### Añadido
- `mth models` muestra también al planificador, fijo en `opus`; no sale de `[models]` y no se puede configurar. (SPEC-0023)
- El agente planificador solo se lanza con `model: "opus"`: `mth-develop` lo exige y la plantilla de encargo de `mth-plan` declara «Modelo: opus». Si el encargo no lo indica, el agente avisa. (SPEC-0023)
- `mth secrets --staged` escanea con `gitleaks` solo lo preparado para el commit. Falla cerrado: sin `gitleaks`, con un error de la herramienta o al agotar el tiempo, no da nada por limpio. Requiere `gitleaks` 8.19.0 o posterior. (SPEC-0024, ADR-0022)
- Hook `pre-commit` opcional (`secrets.hook = "on"`) que rechaza el commit si hay secretos preparados. `hooks.pre_commit` (`own`, `replace`, `chain`) decide cómo convive con un hook ajeno. `git commit --no-verify` lo salta. (SPEC-0024, ADR-0022)
- Workflow de CI opcional `.github/workflows/secrets.yml` (`secrets.ci = "on"`, solo con GitHub y CI exigida) que escanea cada PR y cada push a `main` y `development` con un binario de `gitleaks` fijado. `mth` lo escribe con una marca en la primera línea y no sobrescribe un fichero ajeno. La protección de rama debe exigir su comprobación, porque una rama puede editarlo. (SPEC-0024, ADR-0022)
- La adopción incluye la pregunta `secretos` (`bloquear`, `integrar`, `ninguno`); un repo nuevo hace como mucho seis preguntas, en dos rondas. `mth update` lista las brechas `secretos-hook` y `secretos-ci` (decisión) y `secretos-workflow` (automática), y `mth doctor` informa del estado y de la versión de `gitleaks`. (SPEC-0024, ADR-0022)
- Las claves nuevas `secrets.hook` y `secrets.ci` nacen sin decidir (`""`) y `hooks.pre_commit` es `own`. Un plugin anterior las rechaza al cargar la configuración: actualiza el plugin antes de aceptar las brechas. Ni el hook ni el workflow se activan solos. (SPEC-0024, ADR-0022)
- `mth tools` lista las herramientas externas que usa `mth` (hoy `gitleaks`), su versión, su origen (`PATH`, `gestionada` o `ausente`) y la versión encontrada, sin usar la red. (SPEC-0025, ADR-0023)
- `mth tools install` (con `--force` para reinstalar) descarga la herramienta a una caché del usuario (`MTH_TOOLS_DIR` o el directorio de caché del sistema) tras comprobar su SHA-256; `mth tools prune` borra las versiones que ya no están en el manifiesto. No se descarga nada sin esa orden explícita. (SPEC-0025, ADR-0023)
- `mth secrets` y `mth doctor` usan `gitleaks` del `PATH` si alcanza la versión mínima y, si no, la copia gestionada. Sin ninguna, el error indica `mth tools install gitleaks`; `mth doctor` informa del origen y avisa de copias gestionadas de otra versión. (SPEC-0025, ADR-0023)

## [0.16.0] - 2026-11-26

### Añadido
- Toda idea `feat`, `fix` o `hotfix` necesita un plan acordado con la persona antes de crear la rama. El plan es un fichero local `.work/plans/PLAN-NNNN-slug.md` que no se commitea. (SPEC-0023)
- `mth plan new`, `agree`, `list`, `show` y `done` gestionan los planes acordados. `mth branch --plan PLAN-NNNN` crea la rama contra un plan acordado y `mth integrate` y `mth hotfix finish` exigen que la rama figure en un plan en curso. (SPEC-0023)
- Sección `[plans]` (`required_for`, por defecto `feat`, `fix` y `hotfix`) y clave `[roles].planner` en `.claude/methodology.toml`. (SPEC-0023)
- Agente del plugin `planificador` (siempre Opus, solo lectura): redacta el plan y recomienda los agentes del catálogo que conviene instalar. (SPEC-0023)
- Skill `mth-plan` para redactar, discutir y acordar el plan; el ciclo de `mth-develop` y las reglas base incluyen el paso «plan acordado». (SPEC-0023)
- El `orquestador` (1.1.0) instala los agentes del catálogo que el plan recomienda y reparte el trabajo según el plan. El `verificador` avisa si el diff se sale del plan. (SPEC-0023)
- Gate de secretos en el historial: con `secrets.mode = "block"`, `mth integrate` escanea con `gitleaks` los commits de la rama antes de subirla y bloquea ante un hallazgo nuevo. Los hallazgos se muestran sin el valor del secreto y el informe temporal se borra siempre. (SPEC-0022)
- `mth secrets` escanea la rama o, con `--history`, todo el historial; `--history --accept` acepta los hallazgos ya existentes en una línea base (`secrets.baseline`) y recuerda que hay que rotarlos. (SPEC-0022)
- `mth update --plan` señala la brecha `secretos` (decisión) mientras `secrets.mode` esté sin decidir; `mth doctor` avisa del modo y de la falta de `gitleaks`. Nunca se activa en silencio. (SPEC-0022)
- `revisor-seguridad` 1.1.0 vigila los cambios de `secrets.mode` y de la línea base. (SPEC-0022)

### Corregido
- Las skills, `PRINCIPLES.md` y los mensajes de `mth` ya no citan specs ni ADR de claude-methodology: en otro repo esos números no existen o significan otra cosa y confundían al modelo. Un test impide que vuelvan.

## [0.15.0] - 2026-11-26

### Añadido
- `mth update --plan` lista las brechas entre un repo adoptado y lo que exige el plugin instalado (configuración, agentes del catálogo, bloque de CLAUDE.md, hook, formato de specs y ADR). (SPEC-0021, ADR-0017)
- `mth update` aplica en `chore/update-methodology` las brechas deterministas sin cambiar ninguna decisión ya tomada y deja un ADR de actualización. (SPEC-0021, ADR-0017)
- Skill `mth-update`: la persona la invoca cuando el plugin se ha actualizado; conduce las decisiones y migraciones y se integra por PR. (SPEC-0021, ADR-0017)

### Corregido
- **Catálogo de agentes**: los agentes, los guards y el shim que instala `mth agents add` ya no citan specs ni ADR internos del plugin (SPEC-0012, ADR-0008, ADR-0015…). Un repo adoptado no los define, así que `mth trace` fallaba y bloqueaba su integración. Si ya tienes agentes instalados, `mth agents sync` los actualiza. (SPEC-0012)
- **Adopción y reestructuración**: los ADR que genera `mth init` y `mth reconfigure` usan ya el formato compacto (campos Contexto, Decisión, Rechazado, Consecuencias e Impone), como exige el resto de ADR del repo. (SPEC-0004, SPEC-0011)
- **Guard**: el bloqueo de los merges a mano ya no se esquiva con opciones globales (`gh -R owner/repo pr merge`), con un prefijo como `sudo` o `env`, ni con una petición de `gh api` / `glab api` que pueda escribir en un endpoint de merge o una mutación GraphQL de merge. Los merges siguen haciéndose con `mth integrate`, `mth release` o `mth hotfix finish`. (SPEC-0016)
- **Guard**: la petición de confirmación del nivel de autonomía (`until-pr`, `supervised`) ve ahora los mismos comandos que el bloqueo: con prefijos (`sudo git push`), agrupaciones de shell (`(git commit …)`) y continuaciones de línea. El bloqueo de merges a mano también cubre `$(gh pr merge …)` al inicio de un comando, y el guard bloquea los comandos `glab` y los lanzados en segundo plano con `&`. Un fallo interno del guard indica ahora el tipo de excepción. (SPEC-0007, SPEC-0016)

## [0.14.0] - 2026-11-25

### Añadido
- Sección `[limits]` en la configuración: `max_file_lines` (1000 por defecto), `exclude` y `[[limits.exceptions]]`, donde `max_lines` (techo mayor que el límite) y `reason` son obligatorios; una excepción incompleta falla al cargar la configuración. (SPEC-0020, ADR-0016)
- `mth trace` aplica un trinquete sobre la diferencia con la rama padre: es error que la rama cree un fichero por encima del límite, lo haga cruzarlo o lo haga crecer estando ya por encima; también superar el techo de una excepción y una excepción caducada. Un fichero largo heredado que la rama no hace crecer solo avisa (`mth trace --limits` los lista). Se excluyen los binarios (los que `git` marca como tales o con un byte NUL) y los renombrados que git detecta se comparan con su origen. (SPEC-0020, ADR-0016)
- `revisor-diseno` (1.1.0) valora si el `reason` de cada excepción se sostiene frente a la responsabilidad única, con evals nuevas. (SPEC-0020, ADR-0016)

## [0.13.0] - 2026-11-25

### Añadido
- Cada test declara por qué existe con una etiqueta en su comentario: `verifies: SPEC-NNNN/AC-NN` (o `/FM-NN`), `regression:` con una referencia o `unit:` con un símbolo público. `mth trace` reporta como error un test sin etiqueta y `mth integrate` se detiene; en ficheros legados (`trace.legacy_base`) es solo un aviso. (SPEC-0019, ADR-0015)
- `trace.test_patterns` (glob → regex de la línea que abre un test) con valores por defecto para Python, JS/TS y Go; en otro lenguaje se exige al menos una etiqueta por fichero de tests. (SPEC-0019, ADR-0015)
- `mth trace` avisa de los criterios con un único test (`mth trace --single` los lista), sin cambiar el código de salida. (SPEC-0019, ADR-0015)
- Triangulación en PRINCIPLES §6 (dos ejemplos de clases distintas por AC con entrada variable), ciclo en `mth-develop`, criterios nuevos en `revisor-parsimonia` (tests de la misma clase) y `revisor-fallos` (casos especiales para los valores del test, bloqueante), con sus evals. Ambos revisores pasan a 1.1.0. (SPEC-0019, ADR-0015)

### Cambiado
- **Cambio incompatible (`BREAKING CHANGE`).** Un repo adoptado con tests sin etiquetar verá errores en `mth trace` y `mth integrate` bloqueado. Para migrar, elige una de las dos: 1. Etiqueta los tests: añade en cada uno un comentario `# verifies: SPEC-NNNN/AC-NN` (o `/FM-NN`), `# regression:` con el issue o `# unit:` con la función. `mth trace` lista fichero y línea. 2. Declara lo anterior como heredado: pon en `trace.legacy_base` el commit actual de `development`. Sus tests sin etiqueta quedan como avisos (`mth trace --legacy`) hasta que alguien los toque; los tests nuevos sí deben llevar etiqueta. Si tu lenguaje no es Python, JS/TS ni Go, añade su patrón en `[trace.test_patterns]`; sin él, basta una etiqueta por fichero de tests. (SPEC-0019, ADR-0015)

## [0.12.0] - 2026-11-24

### Añadido
- Formato compacto de specs y ADR: las plantillas (español e inglés) llevan la línea `- Formato: compacto`, criterios de aceptación en EARS (`CUANDO … DEBE …`, `SI … ENTONCES …`, `MIENTRAS …`), modos de fallo con ID `FM-NN` y ADR con campos fijos (`Contexto`, `Decisión`, `Rechazado`, `Consecuencias`, `Impone`). (SPEC-0018, ADR-0014)
- `mth trace` valida ese formato en los documentos que lo declaran y comprueba las referencias `SPEC-NNNN/FM-NN`. Los specs y ADR existentes no cambian. (SPEC-0018, ADR-0014)

### Cambiado
- `context/core.md`, `PRINCIPLES.md`, el bloque de `CLAUDE.md` y las descripciones de skills y agentes se reescriben en estilo compacto, sin perder ninguna regla: −13 % de tokens estimados en lo que se carga siempre (2,8 k → 2,4 k) y −11 % contando `PRINCIPLES.md` (8,5 k → 7,5 k). (SPEC-0018, ADR-0014)
- `PRINCIPLES.md` §7 fija el estilo compacto y `revisor-adr` revisa que los documentos compactos lo cumplan. (SPEC-0018, ADR-0014)

## [0.11.0] - 2026-11-24

### Añadido
- `mth release --plan` decide, sin escribir nada, si hay que publicar y con qué nivel: imprime los fragmentos con su nivel, el nivel resultante (SemVer), la versión propuesta y una decisión con sus motivos (`publicar`, `esperar`, `no publicar` o `bloqueado`), que queda en la traza. (SPEC-0017, ADR-0013)
- Cada fragmento tiene un nivel mínimo: `feat` → `minor`, el resto → `patch`, y eliminar funcionalidad (sección `Eliminado`) → `minor` en `0.y.z` y `major` desde `1.0.0`. `mth integrate` y `mth release` rechazan un `bump` por debajo del mínimo. (SPEC-0017, ADR-0013)
- `mth release --allow-major`: `1.0.0` declara la API estable y solo se publica con esa decisión explícita; sin ella, un nivel `major` antes de `1.0.0` queda bloqueado. (SPEC-0017, ADR-0013)
- Clave `forge` (`github`, `gitlab` o `none`), deducida de la URL del remoto en la adopción (pregunta `forja`, siempre deducida) y escrita por `mth init`. Con `github` nada cambia. (SPEC-0016, ADR-0012)
- Con `gitlab` o `none`, `mth integrate` y `mth release` hacen solo la parte local y terminan con la lista de pasos manuales, sin llamar a `gh` y sin fusionar: `integrate` deja el título y la descripción del MR en `.work/merge-request/`, y `release` prepara `release/vX.Y.Z` con el `CHANGELOG.md` y marca los pasos que git confirma al repetirse. (SPEC-0016, ADR-0012)
- El guard bloquea `glab mr merge` igual que `gh pr merge`. (SPEC-0016, ADR-0012)

### Cambiado
- Las skills `mth-release` y `mth-develop` indican que, tras integrar en `development`, el agente decide solo si publicar con `mth release --plan` y publica cuando recomienda `publicar`. (SPEC-0017, ADR-0013)
- Sin GitHub, la adopción deduce `ci: sin-ci` y `versiones: continuar` (con etiquetas con prefijo y sin herramienta de publicación) en lugar de desactivar `mth integrate` y `mth release`; el plan previo las muestra como activas solo en su parte local. (SPEC-0016, ADR-0012)
- `mth doctor` no pide `gh` ni `ci.required` cuando `forge` no es `github`. (SPEC-0016, ADR-0012)
- `mth hotfix finish` falla antes de tocar nada con `gitlab` o `none`: fusionar sin poder comprobar la CI sería degradar. (SPEC-0016, ADR-0012)

## [0.10.0] - 2026-11-24

### Añadido
- La adopción resuelve en código cada pregunta como `deducida`, `por_defecto` o `decision`, y solo pregunta las decisiones, en una sola ronda y empezando por la precedencia entre el repo y la metodología. Se deducen la rama de integración, el hook `commit-msg` ajeno, el comando de tests de `Makefile` o `justfile`, el idioma, el modo legado y, sin GitHub, la CI y la publicación (`mth survey --json` da `outcome`, `answer`, `basis` y `options` de cada pregunta). (SPEC-0015, ADR-0011)
- `mth init --answers FICHERO --plan` muestra, sin escribir nada, lo deducido, lo que va por defecto, lo decidido y las capacidades activas y desactivadas con su motivo; la adopción imprime el mismo plan antes de escribir. (SPEC-0015, ADR-0011)
- El ADR de adopción registra el resultado de cada pregunta en una columna nueva. (SPEC-0015, ADR-0011)
- La respuesta `revisores` admite `paths` para limitar un revisor del repo a unas rutas (`[review.paths]`). (SPEC-0015, ADR-0011)

### Cambiado
- Una opción que no funciona con el repo (por ejemplo, `ci: crear` o `versiones: continuar` sin GitHub) ya no se ofrece, y `mth init --answers` la rechaza. (SPEC-0015, ADR-0011)
- Las preguntas se ordenan por dependencia: `instrucciones` y `autonomia` van primero (también en `mth reconfigure`). (SPEC-0015, ADR-0011)

### Eliminado
- La opción `commits: sustituir`: un hook `commit-msg` ajeno solo se encadena, porque sustituirlo quitaba controles. (SPEC-0015, ADR-0011)

## [0.9.0] - 2026-11-24

### Añadido
- `mth smoke` comprueba con el Claude Code real que el guard de los agentes bloquea: lanza un subagente canario en un repositorio temporal y da tres resultados (pasa, falla, no concluyente). Pasa solo si el registro del guard muestra el comando del canario bloqueado y una escritura permitida (control positivo) que sí se ejecutó, y el comando prohibido no dejó efecto; que el comando no se ejecutara no basta, porque el sistema de permisos también puede impedirlo. No toca el repo desde el que se lanza, limpia siempre, y acota el coste (modelo `haiku`, 8 turnos, 0,5 USD, 180 s). (SPEC-0014, ADR-0010) (SPEC-0014, ADR-0010)
- Al pasar, registra la versión de Claude Code que se probó. Con agentes del catálogo instalados, `mth session` y `mth doctor` avisan si no hay registro o si Claude Code ha cambiado desde la última prueba de humo. (SPEC-0014) (SPEC-0014, ADR-0010)
- La redacción de credenciales de los registros del guard y de `mth smoke` cubre también los usuarios y claves de una URL (`https://usuario:clave@host`) y los `Bearer` sueltos. (SPEC-0014) (SPEC-0014, ADR-0010)

## [0.8.2] - 2026-11-23

### Corregido
- `mth review record` ya no se fía del número que declara el revisor: cuenta él mismo los hallazgos `[bloqueante]` de `HALLAZGOS` y contrasta la línea `BLOQUEANTES`. Una discrepancia o un informe ilegible (sección ausente, viñetas, texto suelto, severidad desconocida, vacío, ausente o de más de 256 KiB) se registra como revisión **fallida**: no aprueba nada, `mth review status` muestra el motivo y `mth integrate` la rechaza. (SPEC-0013) (SPEC-0013, ADR-0009)
- El informe de cada intento se archiva byte a byte en `.work/reviews/ (un fichero por commit, agente e intento)` sin sobrescribir nunca, y el registro guarda su `sha256` y el número de intentos por agente y commit, para ver si el fallo está en el prompt del revisor. Ante un fallo, la skill `mth-review` pide una única corrección al mismo agente con `SendMessage`. (SPEC-0013, ADR-0009) (SPEC-0013, ADR-0009)

## [0.8.1] - 2026-11-23

### Corregido
- Un agente del catálogo que pierde la cabecera de su `.md` ya no queda sin restricciones: si tiene guard, se bloquea hasta `mth agents sync --force` o `mth agents remove`, y `mth doctor` lo avisa. (SPEC-0012)
- El guard de los agentes de solo lectura ya no se puede sortear con un programa con ruta (`./git`), expansiones de shell (`$'…'`, llaves, comodines), abreviaturas y grupos de opciones prohibidas (`git grep --open=sh`, `git grep -nOsh`, `gh api -iXPOST`) ni filtros que escriben o leen el entorno (`sort -o`, `uniq entrada salida`, `jq -n env`). `respondedor-incidencias` ya no admite `git fetch` ni `git branch -r -d`. (SPEC-0012)
- Los trabajadores no pueden escribir en los ficheros que definen sus propias restricciones (`.claude/hooks/`, `.claude/mth/`, `.claude/agents/`, `.claude/settings*.json`, `.git`). (SPEC-0012)
- El guard tiene límites de tiempo, también en macOS sin `timeout` (con `perl`; sin ninguno de los dos, bloquea): si `git` o el guard no responden, bloquea en lugar de dejar que el hook venza y la llamada pase. La protección de ficheros ignora las mayúsculas, como los sistemas de ficheros de macOS y Windows. (SPEC-0012)
- Sin lanzador (plugin ausente o anterior a 0.8.0), solo se bloquea a los agentes del catálogo; `verificador`, `documentador` y los demás siguen funcionando. (SPEC-0012)
- `mth agents add` escribe el shim y la entrada del hook antes que los agentes, con escrituras atómicas, y al quitar el hook conserva los hooks propios que compartan entrada. (SPEC-0012)
- `mth db-query` solo abre bases dentro del repositorio, exige límites positivos y acota la longitud de los valores y de las celdas. (SPEC-0012)
- Cada decisión del guard sobre un agente del catálogo queda registrada en `.git/mth/agent-guard.jsonl` (privado, sin el comando completo y con las credenciales redactadas), con traceback si es un error interno; el shim registra los bloqueos que decide él mismo (sin lanzador, o una salida inesperada del guard) con hora, agente, sesión y herramienta. (SPEC-0012)
- `mth agents` informa de un fallo al escribir un fichero (disco lleno, permisos) como un error reanudable y no como un bug, y conserva los permisos de los ficheros que reescribe. (SPEC-0012)

## [0.8.0] - 2026-11-23

### Añadido
- Catálogo de 12 plantillas de agentes (cinco revisores, `diagnosticador`, `explorador-specs`, cuatro opcionales y el `orquestador` experimental) en tres perfiles: `base`, `opcional` y `autonomo`. No están activas: `mth agents list|add|sync|diff|remove` las instala en `.claude/agents/`, renderizadas de forma determinista con la configuración y `[agents.*]`, y las mantiene al día conservando la sección local de cada repo. Los revisores se colocan en `review.agents` según su orden. Guía en `docs/catalogo-de-agentes.md`. (SPEC-0012, ADR-0008)
- Guard por agente: `mth agents add` deja una entrada `PreToolUse` en `.claude/settings.json` y el shim `.claude/hooks/mth-agent-guard`; `mth agent-guard` aplica a cada agente del catálogo sus propias reglas y falla cerrado. `mth session` registra el lanzador que usa el shim. (SPEC-0012, ADR-0008)
- `mth db-query --db ALIAS`: consultas SQLite estrictamente de solo lectura para el agente `lector-estado`, con límite de filas y de tiempo. (SPEC-0012, ADR-0008)
- `mth init` ofrece el perfil `base` en la pregunta `revisores`, y `mth doctor` avisa de agentes desactualizados, editados a mano o sin guard. (SPEC-0012, ADR-0008)

### Cambiado
- La pregunta `revisores` de la adopción se hace en todos los perfiles, también en un repo nuevo sin agentes. (SPEC-0012, ADR-0008)
- Nueva tabla opcional `[agents.*]` en `.claude/methodology.toml`. Un plugin anterior a esta versión la rechaza como clave desconocida: actualiza el plugin en todo el equipo antes de añadirla. (SPEC-0012, ADR-0008)

## [0.7.1] - 2026-11-18

### Añadido
- Licencia MIT (`LICENSE`), declarada también en `plugin.json`. El repositorio es público: se instala con `/plugin marketplace add Ascass0/claude-methodology` sin ninguna credencial.

## [0.7.0] - 2026-11-18

### Añadido
- Skill `mth-reconfigure`: en un repo ya adoptado, vuelve a pasar la entrevista de la adopción. Se puede rehacer el formulario completo, revisar bloques (`flujo`, `documentacion`, `calidad`, `agente`) o cambiar solo una decisión. (SPEC-0011, ADR-0007)
- `mth survey --reconfigure [--only …]`: inventario de un repo adoptado con cada pregunta aplicable y su valor actual. (SPEC-0011, ADR-0007)
- `mth reconfigure --answers FICHERO [--only …]`: valida las respuestas y las aplica sobre la configuración actual, conservando lo que no se pregunta. Abre `chore/reconfigure-methodology` con la configuración nueva y un ADR de reestructuración que lista cada clave que cambia. Si las respuestas no cambian nada, o no se pueden aplicar, no crea nada. (SPEC-0011, ADR-0007)
- Con `autonomy.level = "supervised"`, el guard pide confirmación para `mth reconfigure`. (SPEC-0011, ADR-0007)
- Directorio de trabajo local `.work/` en cada repo adoptado, con `plans/`, `merge-request/`, `security-report/`, `reviews/`, `notes/` y `tmp/`: ahí deja Claude planes, manifiestos, cuerpos de PR, informes y notas, en lugar del scratchpad de la sesión. El hook de sesión y `mth init` lo crean y lo excluyen de git en `.git/info/exclude`, sin modificar ningún fichero versionado. `mth doctor` lo comprueba y el guard bloquea los `git add` forzados que lo incluirían. (SPEC-0010, ADR-0006)
- `work.dirs` en `.claude/methodology.toml` añade subdirectorios propios del repo a `.work/`. (SPEC-0010, ADR-0006)

### Cambiado
- `mth-review` guarda los informes de los revisores en `.work/reviews/`, `mth-develop` los manifiestos de los agentes en `.work/plans/` y `mth-integrate` propone `.work/merge-request/` para los resúmenes largos de PR. (SPEC-0010, ADR-0006)

## [0.6.0] - 2026-11-18

### Añadido
- Adopción guiada: `mth survey` inventaria el repo sin modificarlo, la skill `mth-init` conduce una entrevista con Opus que solo pregunta lo necesario, y `mth init --answers FICHERO` convierte las respuestas en configuración y en el ADR de adopción. `mth init --decline` desactiva el plugin en ese repo (`.claude/settings.local.json`, no versionado). (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `trace.legacy_base` y `mth trace --legacy`: en una adopción gradual, los hallazgos en ficheros sin cambios desde el commit base son avisos; lo que se toca después cumple todas las reglas. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `hooks.commit_msg` con los valores `own`, `replace` y `chain`: decide qué hacer con un hook `commit-msg` ajeno al instalar el de `mth`. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `autonomy.level` con los valores `full`, `until-pr` y `supervised`: el guard pide confirmación para integrar y publicar, o también para ramas, commits y push. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `language.docs` con los valores `es` y `en`: idioma de docs, specs, ADR, changelog y PR, con plantillas en inglés. Código y commits siguen en inglés. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- Nueva lista `release.version_files` en `.claude/methodology.toml` para declarar los ficheros que contienen la versión del proyecto (`package.json`, `pyproject.toml`, `plugin.json`…). Cada entrada tiene `path` (ruta relativa al repo) y `pattern` (expresión regular con exactamente un grupo de captura: la versión). Por defecto está vacía. Una entrada inválida (claves que faltan o sobran, ruta absoluta o con `..`, regex inválida o sin exactamente un grupo, entrada duplicada) hace fallar la carga de la configuración y ningún comando `mth` se ejecuta hasta corregirla. (SPEC-0003)
- `mth release` y `mth hotfix finish` comprueban estos ficheros antes de crear la rama o el commit de la versión: deben existir y el patrón debe aparecer exactamente una vez; si no, no publican ni modifican nada. Después sustituyen la versión en el mismo commit `chore(release)` que el CHANGELOG y listan los ficheros actualizados en su cuerpo. (SPEC-0003)
- `mth doctor` muestra la versión que declara cada fichero: ✓ si coincide con la última etiqueta, ⚠ si está desfasada y ✗ si el fichero no existe o el patrón no aparece exactamente una vez. (SPEC-0003)
- La plantilla de `methodology.toml` incluye un ejemplo de `release.version_files`. (SPEC-0003)

### Cambiado
- En un repo sin `.claude/methodology.toml`, el plugin ya no inyecta las reglas base ni bloquea comandos: el hook de sesión solo da el aviso de adopción y el guard no actúa hasta que se adopta. (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- `PRINCIPLES.md` §5 (idioma del código, independiente del de la documentación), §7 (idioma de `language.docs`) y §11 (autonomía según `autonomy.level`). (SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005)
- Las claves que añade esta versión (`language`, `hooks`, `autonomy`, `trace.legacy_base` y `release.version_files`) bloquean a quien siga con la 0.5.x: ningún comando `mth` se ejecuta y su hook `commit-msg` rechaza los commits. Actualiza el plugin en todo el equipo antes de añadirlas; el README explica el orden en "Actualizar el plugin". (SPEC-0009)

### Corregido
- El error de clave desconocida en `.claude/methodology.toml` indica la versión del plugin que la rechaza y explica que, si no es una errata, hay que actualizar el plugin con `/plugin` y abrir una sesión nueva. `mth doctor` muestra ahora también la pista de los errores de configuración. (SPEC-0009)
- Al publicar, los ficheros de `release.version_files` conservan sus finales de línea: un fichero con CRLF ya no se reescribe entero con LF. (SPEC-0003)
- Un patrón de `release.version_files` cuyo grupo de captura es opcional y no captura nada ya no corrompe el fichero al publicar: `mth release`, `mth hotfix finish` y `mth doctor` lo rechazan sin modificar nada. (SPEC-0003)

## [0.5.1] - 2026-11-18

### Corregido
- El plugin declara su versión real (0.5.1) en `plugin.json`, en el marketplace y en `mth --version`. La 0.5.0 se publicó declarando 0.4.0, así que Claude Code no ofrecía la actualización a quien ya tenía instalado el plugin: actualiza para recibir los cambios de la 0.5.0. (SPEC-0001, SPEC-0002)
- El CHANGELOG incluye la sección de la 0.5.0 (delegación verificable y niveles de modelo), que faltaba. (SPEC-0001, SPEC-0002)

## [0.5.0] - 2026-11-18

### Añadido
- Plan de trabajo en la spec (sección `## Plan de trabajo`): tareas por oleadas con sus ficheros permitidos y sus criterios. `mth plan check SPEC-NNNN` lo valida antes de delegar: formato, criterios existentes y asignados, y que dos tareas de la misma oleada no compartan ficheros. `mth trace` aplica las mismas comprobaciones a toda spec que tenga la sección. (SPEC-0001, ADR-0001)
- `mth plan verify SPEC-NNNN --wave N --manifest FICHERO …` verifica una oleada contra los manifiestos JSON de sus agentes: rechaza tareas sin manifiesto (no ejecutadas), bloqueadas o fallidas (no completadas), manifiestos inválidos, criterios sin cubrir, tests ausentes o en rojo, ficheros fuera del alcance de la tarea, cambios que nadie declara y ficheros declarados sin cambios reales. Los desvíos se muestran como avisos. (SPEC-0001, ADR-0001)
- `mth-develop` describe el protocolo de delegación por oleadas: encargo con los ficheros permitidos de la tarea, manifiesto JSON guardado sin editar, verificación al cerrar cada oleada y un único reintento por tarea fallida. (SPEC-0001, ADR-0001)
- Tabla `[models]` en `.claude/methodology.toml`: escalera de reintento (`ladder`, por defecto `haiku`, `sonnet`, `opus`) y nivel de las tareas, de los revisores y del documentador. `mth models` la muestra y una configuración inválida falla antes de ejecutar nada. (SPEC-0002, ADR-0002)
- Columna opcional `Modelo` en el plan de trabajo de la spec: cada tarea declara el modelo que necesita; si la celda está vacía, se usa `models.task`. (SPEC-0002, ADR-0002)
- `mth plan model SPEC-NNNN T-NN [--retry]` imprime el alias que hay que pasar a la herramienta Agent; con `--retry`, el siguiente nivel de la escalera, de modo que un reintento no repite el modelo que falló. (SPEC-0002, ADR-0002)
- `mth plan verify --model T-NN=alias` indica con qué modelo se ejecutó cada tarea y registra un evento `plan.task` por tarea (modelo, resultado y huella del manifiesto) en `.git/mth/trace.jsonl`. (SPEC-0002, ADR-0002)
- `mth plan stats [--spec SPEC-NNNN]` resume por modelo los intentos, los aciertos y el porcentaje de `ok`, para ajustar los niveles con evidencia. (SPEC-0002, ADR-0002)
- Las skills usan esos niveles: `mth-develop` elige el modelo de cada tarea delegada, escala en el reintento y lanza el documentador con `models.documenter`; `mth-review` lanza los revisores con `models.review`. (SPEC-0002, ADR-0002)

### Cambiado
- `mth review record` exige `--report INFORME` y toma el número de bloqueantes de la última línea del informe del revisor (`BLOQUEANTES: N`). Un informe ausente, vacío, de más de 256 KiB o sin esa línea no se registra y la revisión sigue pendiente. `--blocking` desaparece: actualiza los scripts o hábitos que lo usen. (SPEC-0001, ADR-0001)
- `mth plan check` muestra el modelo efectivo de cada tarea, por ejemplo `Oleada 1: T-01 (haiku), T-02 (sonnet)`. (SPEC-0002, ADR-0002)

## [0.4.0] - 2026-11-18

### Añadido
- SOLID como práctica de diseño obligatoria en clases, módulos y componentes (apartado 2 de `PRINCIPLES.md`), aplicada con proporcionalidad: los puntos de extensión solo se crean con variantes reales.
- Principios contra los antipatrones STUPID: dependencias explícitas sin estado global oculto, bajo acoplamiento, testable por diseño y optimización con evidencia (apartado 2 de `PRINCIPLES.md`); nombres que revelan intención y sin duplicación de conocimiento (apartado 5). Las reglas base de sesión los resumen.

## [0.3.1] - 2026-11-10

### Añadido
- Protocolo de orquestación en `mth-develop`: la sesión principal divide la spec en tareas con ficheros disjuntos, delega en los agentes `dev-*` del repo con un encargo autocontenido y recibe un manifiesto; los commits los hace siempre la sesión principal.

## [0.3.0] - 2026-11-10

### Añadido
- Agentes compartidos en el plugin: `verificador` (cumplimiento real de la spec, tests válidos, regresión y afirmaciones falsas) y `documentador` (docs, fragmento y registros documentales del repo).
- Revisores condicionales por rutas (`[review.paths]`, globs con negación `!`): solo se exigen si el diff toca su área. `mth review status` muestra los obligatorios de la rama.
- `mth doctor` reconoce los agentes del plugin además de los del repo.

### Cambiado
- Todas las llamadas a `gh` indican el repositorio de `origin` (`--repo`): nunca se elige entre `origin` y `upstream` por defecto.
- La plantilla declara `verificador` como primer revisor y los roles `documenter` y `verifier`.

## [0.2.1] - 2026-11-10

### Corregido
- Los hooks y el hook `commit-msg` usan un lanzador que busca un Python >= 3.11 en lugar de depender de `python3`: con pyenv o un venv en una versión anterior, el guard quedaba desactivado sin avisar y el contexto de sesión no se inyectaba. `MTH_PYTHON` permite fijar el intérprete.

## [0.2.0] - 2026-11-10

### Añadido
- Soporte de forks: `release.tag_prefix`, `commits.external_refs`, `trace.include` y `paths.claude_md`.
- `mth init --config` adopta la metodología con una configuración preparada, validada antes de tocar el repo.
- Ramas de primer nivel `security` con sección y bump propios en el fragmento.

### Cambiado
- Los mensajes de merge listan como máximo 50 commits propios.

## [0.1.0] - 2026-11-10

### Añadido
- Principios de desarrollo con precedencia explícita y mecanismo de imposición por regla.
- CLI determinista `mth`: ramas, commits validados, sync, integración por PR con merge commit, releases y hotfixes reanudables.
- Trazabilidad: IDs definidos y únicos, referencias, enlaces internos y cobertura de criterios de aceptación.
- Changelog por fragmentos agregado en cada versión.
- Hooks de Claude Code: contexto de sesión y guard contra reescritura de historia.
- Skills `mth-*` para todo el ciclo.
