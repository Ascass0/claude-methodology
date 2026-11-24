# SPEC-0014 · Prueba de humo de los agentes

- Estado: implementada
- Fecha: 2026-11-23
- ADRs: [ADR-0010](../adr/process/ADR-0010-la-prueba-de-humo-exige-evidencia-independiente-del-guard.md), [ADR-0008](../adr/process/ADR-0008-catalogo-de-plantillas-de-agentes.md)
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0014/AC-NN`. -->

## Contexto

El guard por agente ([SPEC-0012](SPEC-0012-catalogo-de-agentes.md)) solo restringe a un agente si Claude Code envía `agent_id` y `agent_type` al hook de `.claude/settings.json`. Es un comportamiento externo que puede cambiar con cualquier versión, y entonces el guard falla abierto sin aviso. La comprobación era un procedimiento manual. Esta spec la automatiza (`mth smoke`) y hace que `mth` avise cuando Claude Code ha cambiado desde la última vez que se comprobó.

## Objetivo

1. `mth smoke` comprueba, con el Claude Code real, que el guard bloquea a un subagente y permite lo que debe, con tres resultados: pasa, falla, no concluyente.
2. «Pasa» exige evidencia independiente: ni la ausencia de un comando ni el código de salida bastan.
3. La prueba no toca el repo de quien la lanza, tiene coste acotado y se limpia siempre.
4. La versión comprobada queda registrada y `mth session` y `mth doctor` avisan si Claude Code ha cambiado.

## Fuera de alcance

- Ejecutarla en CI o a intervalos: la lanza quien opera el repo.
- Probar cada agente del catálogo o cada herramienta (`Edit`, `MultiEdit`, `NotebookEdit`): el canario ejerce `Bash` y `Write`; las reglas de cada agente las cubren los casos `[[guard]]`.
- Probar el aislamiento `isolation: worktree`.
- Windows nativo.

## Comportamiento

### Uso

`mth smoke [--claude RUTA] [--model MODELO] [--timeout SEGUNDOS]`. Códigos de salida: **0** pasa, **1** falla, **3** no concluyente (2 queda para los errores de uso, como en el resto de `mth`).

La CLI `claude` se busca en este orden: `--claude`, la variable `MTH_CLAUDE` (rutas absolutas: una relativa se resolvería contra un fichero del repo), `CLAUDE_CODE_EXECPATH` (el ejecutable de la sesión en curso, que es la versión que de verdad se usa) y el `PATH`. Si no se encuentra, el resultado es no concluyente.

### Repositorio temporal

Se crea en un directorio temporal, fuera del repo, y se borra en todos los caminos (éxito, fallo, no concluyente, plazo agotado, interrupción). Contiene: un `git init` con un commit; el shim del guard y la entrada `PreToolUse` de `.claude/settings.json`, instalados con las mismas funciones que `mth agents add`; el lanzador registrado con el intérprete y el `mth.py` en uso; y el canario.

El canario `mth-canary` no existe en el catálogo: solo vive en el repo temporal, así que no aparece en `mth agents list` ni en el repo de quien lo lanza. Su `.md` lleva la cabecera de plantilla y su guard es:

- `[bash] mode = "deny"`: ningún comando.
- `[write] allow = ["canary-ok.txt"]`: solo ese fichero, en la raíz del repo temporal.

### Encargo y límites

`claude -p` con el encargo de usar el subagente `mth-canary` para (1) escribir `canary-ok.txt` con el texto `mth-canary` y (2) ejecutar `touch canary-leak.txt`. Los permisos no deben decidir la prueba: en modo no interactivo Claude Code deniega por defecto la escritura («you haven't granted it yet») y daría un control positivo que nunca se ejecuta. Se concede exactamente lo que el canario debe hacer, sobre las rutas exactas del repo temporal, de modo que un comando prohibido que se ejecute sea un fallo del guard y no del sistema de permisos. Parámetros fijos: modelo barato por defecto (`haiku`), `--max-turns 8`, `--max-budget-usd 0.5`, `--no-session-persistence`, `--setting-sources project` (no cargan los ajustes ni plugins del usuario), `--allowedTools` con dos reglas exactas, `Edit(//<repo>/canary-ok.txt)` (las reglas de archivo se llaman `Edit` y cubren `Write`) y `Bash(touch <repo>/canary-leak.txt)`, plazo de 180 s por defecto. Al vencer el plazo, o al terminar, se mata el grupo de procesos de `claude`.

`claude` recibe un **entorno mínimo**, no el de quien lanza la prueba: `HOME`, `PATH`, `TMPDIR`, locale, proxies y certificados, `CLAUDE_CONFIG_DIR`, y `ANTHROPIC_*`, `CLAUDE_CODE_USE_*` y `CLAUDE_CODE_OAUTH*`; las credenciales de un proveedor (`AWS_*`, `GOOGLE_*`, `AZURE_*`) pasan solo si ese proveedor está elegido. Si el guard fallara, que es lo que la prueba busca, el comando prohibido correría con ese entorno: no debe llevar `GH_TOKEN` ni claves de nube. Los `git` del repo temporal ignoran la configuración global y las variables `GIT_*` del entorno.

### Evidencia y resultado

Se lee el registro del guard del repo temporal (`<git-common-dir>/mth/agent-guard.jsonl`) y los ficheros:

| Evidencia | Significado |
|---|---|
| decisión `deny` de `Bash` con agente `mth-canary` | el hook recibió `agent_type` y el guard bloqueó |
| decisión `allow` de `Write` con agente `mth-canary` | control positivo: el subagente usa herramientas y el hook está en su camino |
| `canary-ok.txt` con el texto esperado | el control positivo se ejecutó de verdad |
| `canary-leak.txt` existe | el comando prohibido se ejecutó |

- **Pasa**: hay `deny` de `Bash`, hay `allow` de `Write`, `canary-ok.txt` existe y `canary-leak.txt` no.
- **Falla**: `canary-leak.txt` existe, o `canary-ok.txt` existe sin ninguna decisión del guard de `Write` (el hook no estaba en el camino).
- **No concluyente**: cualquier otro caso: sin `claude`, plazo agotado, error de autenticación o de red (la CLI termina con error y sin evidencia), el modelo no llamó a la herramienta, o el sistema de permisos impidió el comando (no hay `deny` del guard ni efecto alguno).

### Registro de la versión

`<git-common-dir>/mth/smoke` (del repo de quien lanza la prueba), JSON con `claude_version` (la salida literal de `claude --version`), `claude_path`, `mth_version` y la fecha. Se escribe solo cuando pasa. Un resultado que falla **borra** el registro; uno no concluyente lo deja como estaba. Un registro ilegible se trata como ausente.

### Avisos

`mth session` y `mth doctor` comparan `claude --version` (misma localización que arriba, con un límite de 2 s) con el registro, solo si hay agentes del catálogo instalados:

- sin registro: «Las restricciones de los agentes del catálogo no se han verificado con Claude Code <versión> (mth smoke).»
- con otra versión: «Claude Code ha cambiado desde la última prueba de humo (<registrada> → <actual>); las restricciones de los agentes no están verificadas (mth smoke).»
- si no se puede determinar la versión, `mth session` calla y `mth doctor` lo dice.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| `claude` no existe o no arranca | Localización / `OSError` | No concluyente; no registra |
| Sin autenticación o sin red | La CLI termina con error y no hay evidencia | No concluyente; muestra la última línea de su salida |
| Plazo agotado | Temporizador | Se mata el grupo de procesos; no concluyente salvo que ya haya evidencia de fallo |
| El modelo no llama a las herramientas | Sin decisiones ni ficheros | No concluyente |
| El sistema de permisos impide el comando | Sin `deny` del guard y sin efecto | No concluyente: nunca pasa |
| El guard no actuó | Existe `canary-leak.txt`, o `canary-ok.txt` sin decisión | Falla; borra el registro de versión |
| No se puede crear el directorio o el repo temporal (disco, `TMPDIR`) | `OSError` / `git` falla | Error accionable; traza `smoke.error`; no registra |
| `claude` desaparece o no puede arrancar después de responder a `--version` | `OSError` al lanzarlo | No concluyente |
| El registro de decisiones del guard no se puede leer | `OSError` distinto de «no existe» | No concluyente (sin fuga): ni se afirma ni se descarta que el guard actuara |
| El entorno del llamador trae `GIT_DIR` o `GIT_COMMON_DIR` | Variables `GIT_*` | Se ignoran en todas las operaciones sobre el repo temporal, que debe resolver bajo su directorio |
| Interrupción (Ctrl+C, SIGTERM) | Señal (el manejador se arma antes de crear el directorio) | Limpia el repo temporal y mata a `claude`; no registra; traza `smoke.interrupted` |
| El registro de versión no se puede escribir | `OSError` | Error reanudable; el resultado se muestra igualmente |
| Registro de versión corrupto | JSON ilegible | Se trata como ausente |
| `claude` en el `PATH` es una entrada relativa o vacía (resolvería a un fichero del repo) | Ruta no absoluta | No se usa |
| `git` no responde al preparar el repo temporal | Plazo de 30 s | Error accionable; no registra |

## Criterios de aceptación

- **AC-01**: Con un Claude Code que entrega `agent_type` al hook y un guard que bloquea, `mth smoke` termina en 0, informa de que pasa y registra la salida literal de `claude --version`.
- **AC-02**: Si el comando prohibido se ejecuta (el hook no actúa), termina en 1, borra el registro de versión y lo dice.
- **AC-03**: Si el subagente no llama a ninguna herramienta, o la CLI falla sin evidencia (autenticación, red), termina en 3 y no cambia el registro de versión.
- **AC-04**: Si no hay `deny` del guard aunque el comando no se ejecutara (lo impidió el sistema de permisos), o falta el control positivo, termina en 3 y no registra: nunca pasa por la mera ausencia del efecto.
- **AC-05**: Si `canary-ok.txt` existe sin ninguna decisión del guard de `Write`, termina en 1.
- **AC-06**: La prueba no crea ni modifica nada en el repo de quien la lanza salvo el registro de versión al pasar; el directorio temporal se borra en todos los caminos, incluido el plazo agotado y la interrupción, y `claude` se detiene.
- **AC-07**: El canario no aparece en `mth agents list`.
- **AC-08**: La línea de órdenes de `claude` lleva el modelo fijo, el máximo de turnos, el tope de coste, `--no-session-persistence`, `--setting-sources project`, la concesión de las dos reglas exactas y se mata al agotar el plazo. El proceso hijo recibe solo el entorno mínimo (sin `GH_TOKEN` ni credenciales de nube ajenas al proveedor elegido).
- **AC-09**: `claude` se localiza por `--claude`, `MTH_CLAUDE`, `CLAUDE_CODE_EXECPATH` y `PATH`, en ese orden; si falta, termina en 3 con una pista.
- **AC-10**: `mth session` y `mth doctor` avisan de que no hay registro o de que la versión cambió, con los textos de esta spec, solo si hay agentes del catálogo instalados, y no avisan si la versión coincide.
- **AC-11**: Un registro de versión corrupto se trata como ausente.
- **AC-12**: Los modos de fallo de la tabla tienen respuesta (incluidos el directorio temporal que no se puede crear, un `claude` que desaparece, un registro del guard ilegible y `GIT_*` heredadas): el plazo agotado con prueba de fallo da fallo; un repo temporal que no se puede construir (o un `git` que no responde) es un error accionable que no registra; un registro que no se puede escribir o borrar no oculta el resultado; una CLI que no arranca es no concluyente; las variables `GIT_*` del entorno no llegan al repo temporal; y cada salida queda en la traza: `smoke.verdict` (cualquiera de los tres resultados, incluidos los tempranos sin `claude`), `smoke.error` (el repo temporal no se pudo preparar) o `smoke.interrupted`.

## Notas

El procedimiento manual de `docs/catalogo-de-agentes.md` sigue siendo válido para quien quiera probar un agente concreto con un subagente real.
