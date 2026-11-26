# SPEC-0024 · Hook de precommit y workflow de CI para secretos

- Estado: borrador
- Fecha: 2026-11-26
- Formato: compacto
- ADRs: [ADR-0022](../adr/security/ADR-0022-hook-de-precommit-y-workflow-de-ci-para-secretos.md)
- Sustituye a: —

## Contexto

- [SPEC-0022](SPEC-0022-gate-de-secretos-en-el-historial.md) escanea al integrar; un secreto ya está en el historial local cuando llega ahí, y quien no usa `mth integrate` no pasa por el gate.
- [ADR-0022](../adr/security/ADR-0022-hook-de-precommit-y-workflow-de-ci-para-secretos.md) añade un hook `pre-commit` local y una plantilla de workflow de CI, ambos opcionales y nunca activados en silencio.
- El hook no se puede imponer a cada clon: la barrera que cuenta es la CI.

## Objetivo

1. Con `secrets.hook = "on"`, un commit con un secreto preparado se rechaza antes de entrar en el historial.
2. Con `secrets.ci = "on"`, cada PR y cada push a `main` y `development` se escanea en la CI.
3. Un repo adoptado se entera de que falta decidir ambas piezas, sin cambiarle nada solo.

## Fuera de alcance

- Otros escáneres distintos de `gitleaks` y otras forjas distintas de GitHub Actions.
- Escanear ficheros sin seguimiento o el mensaje del commit.
- Reescribir o limpiar historia; escaneo de dependencias y análisis estático.
- Impedir que una rama modifique el workflow: lo cubre la protección de rama (ver Notas).

## Comportamiento

### Configuración

| Clave | Por defecto | Significa |
|---|---|---|
| `secrets.hook` | `""` | `""` sin decidir · `"off"` sin hook · `"on"` hook `pre-commit` instalado |
| `secrets.ci` | `""` | `""` sin decidir · `"off"` sin workflow · `"on"` workflow `.github/workflows/secrets.yml` |
| `hooks.pre_commit` | `own` | Como `hooks.commit_msg` ([SPEC-0006](SPEC-0006-hooks-commit-msg-encadenados.md)): `own` no toca un hook ajeno · `replace` lo guarda como `pre-commit.pre-mth` · `chain` lo guarda como `pre-commit.local` y lo ejecuta primero |

`hooks.pre_commit` y `commands.precommit` son cosas distintas: la primera gestiona el fichero del hook de git, la segunda es el comando que `mth commit` ejecuta antes de cada commit.

### `mth secrets --staged`

- Ejecuta `gitleaks git --pre-commit --redact --staged --no-banner --exit-code 2` con el mismo informe temporal, línea base, tiempo límite y salida sin valores que `mth secrets` ([SPEC-0022](SPEC-0022-gate-de-secretos-en-el-historial.md)).
- Funciona con cualquier valor de `secrets.hook`; el valor solo decide si el hook lo invoca.

### Hook `pre-commit`

- Solo existe con `secrets.hook = "on"`. Ejecuta `mth secrets --staged`; si `mth` no se encuentra, rechaza el commit.
- La instalación sigue las mismas reglas que el hook `commit-msg`: idempotente, convive con un hook ajeno según `hooks.pre_commit` y falla sin tocar nada si el directorio de hooks está versionado.
- Con `secrets.hook = "off"`, `mth` retira su hook `pre-commit`; no toca un hook ajeno ni las copias `pre-commit.pre-mth` o `pre-commit.local`.

### Workflow de CI

- Plantilla: `plugins/methodology/templates/workflows/secrets.yml`. `mth` la escribe en `.github/workflows/secrets.yml` con la ruta de `secrets.baseline` sustituida.
- Escanea el rango del PR (`base..head`) y el de cada push a `main` y `development`. Descarga el binario de `gitleaks` con versión y suma de comprobación fijadas y no usa acciones de terceros para escanear; las acciones que usa van fijadas por SHA.
- Solo se escribe con `secrets.ci = "on"`, `forge = github` y `ci.required = true`. Lleva una marca en su primera línea: sin ella el fichero es ajeno y no se toca.

### Entrevista y brechas

- `mth-init` hace la pregunta `secretos` (siempre `decision`) con tres opciones: `bloquear` (`secrets.mode = "block"`, `secrets.hook = "on"` y `secrets.ci = "on"` si hay GitHub y CI exigida), `integrar` (`secrets.mode = "block"`, hook y CI `off`) y `ninguno` (todo `off`). Un repo nuevo hace como mucho seis preguntas.
- `mth update --plan` lista `secretos-hook` (`decision`) mientras `secrets.hook = ""`, y `secretos-ci` (`decision`) mientras `secrets.ci = ""` con GitHub y `ci.required = true`.
- Decididas, `mth update` reinstala el hook y reescribe el workflow cuando faltan o están desactualizados (clase `automatica`).
- `mth doctor` informa del estado de ambos y de la versión de `gitleaks`.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Valor desconocido en `secrets.hook`, `secrets.ci` o `hooks.pre_commit` | Error de configuración que nombra la clave; ningún comando corre | AC-01 |
| FM-02 | `gitleaks` no instalado, falla o no termina al preparar un commit | El commit se rechaza con el remedio; no se da por limpio | AC-04 |
| FM-03 | Secreto preparado | El commit se rechaza; se imprime regla, fichero y línea, nunca el valor | AC-03 |
| FM-04 | Hook `pre-commit` ajeno con `replace` y `pre-commit.pre-mth` ya existente, o directorio de hooks versionado | Error con la instrucción; no se toca ningún fichero | AC-06, AC-07 |
| FM-05 | `pre-commit.local` desaparece o no es ejecutable con `chain` | El hook rechaza el commit y lo explica | AC-06 |
| FM-06 | Ya existe `.github/workflows/secrets.yml` sin la marca | No se sobrescribe; `mth doctor` avisa | AC-10 |
| FM-07 | `secrets.baseline` con caracteres que no sean letras, cifras, `.`, `_`, `-` o `/` | Error; no se escribe el workflow | AC-11 |
| FM-08 | La rama modifica o borra el workflow | No se puede impedir desde el cliente; la protección de rama debe exigir su comprobación y la revisión mira esos ficheros | AC-16 |
| FM-09 | El commit se hace con `--no-verify` | El hook no corre; la CI y `mth integrate` siguen escaneando | AC-09 |

## Criterios de aceptación

- **AC-01**: SI `secrets.hook` o `secrets.ci` no es `""`, `"off"` ni `"on"`, o `hooks.pre_commit` no es `own`, `replace` ni `chain`, ENTONCES la carga de la configuración DEBE fallar nombrando la clave.
- **AC-02**: CUANDO se ejecuta `mth secrets --staged`, `mth` DEBE escanear solo lo preparado con `gitleaks git --pre-commit --redact --staged` y pasar la línea base solo si existe.
- **AC-03**: SI el escaneo de lo preparado encuentra secretos, ENTONCES `mth secrets --staged` DEBE terminar con error listando regla, fichero y línea sin imprimir el valor; sin hallazgos DEBE terminar con éxito.
- **AC-04**: SI `gitleaks` no está instalado, falla o no termina en `SCAN_TIMEOUT` segundos, ENTONCES `mth secrets --staged` DEBE fallar con el remedio y NO DEBE darlo por limpio.
- **AC-05**: MIENTRAS `secrets.hook = "on"`, `mth` DEBE instalar un hook `pre-commit` que ejecute `mth secrets --staged` y rechace el commit si `mth` no se encuentra; con `"off"` DEBE retirar su hook sin tocar uno ajeno ni las copias guardadas.
- **AC-06**: MIENTRAS `hooks.pre_commit = "own"`, un hook `pre-commit` ajeno DEBE quedar intacto; con `replace` DEBE renombrarse a `pre-commit.pre-mth` (y fallar sin tocar nada si la copia existe); con `chain` DEBE renombrarse a `pre-commit.local` y ejecutarse primero, rechazando el commit si lo rechaza o si falta o no es ejecutable.
- **AC-07**: SI el directorio de hooks está dentro del árbol de trabajo, ENTONCES `replace` y `chain` DEBEN fallar con la instrucción de añadir `mth secrets --staged` al hook del gestor, sin modificar nada.
- **AC-08**: CUANDO se instala el hook dos veces, `mth` DEBE dejar el mismo resultado que con una.
- **AC-09**: La plantilla `secrets.yml` DEBE disparar en `pull_request` y en `push` a `main` y `development`, tener permisos de solo lectura, descargar `gitleaks` con versión y SHA-256 fijados, fijar por SHA cada acción que use y no usar acciones de terceros para escanear.
- **AC-10**: MIENTRAS `secrets.ci = "on"`, `forge = github` y `ci.required = true`, `mth` DEBE escribir `.github/workflows/secrets.yml` desde la plantilla con `secrets.baseline` sustituida; un fichero existente sin la marca NO DEBE sobrescribirse.
- **AC-11**: SI `secrets.baseline` contiene caracteres distintos de letras, cifras, `.`, `_`, `-` o `/`, ENTONCES `mth` DEBE negarse a escribir el workflow.
- **AC-12**: MIENTRAS `secrets.hook = ""`, `mth update --plan` DEBE listar la brecha `secretos-hook` de clase `decision`; y MIENTRAS `secrets.ci = ""` con GitHub y `ci.required = true`, la brecha `secretos-ci`; decididas o sin esas condiciones NO DEBEN listarse.
- **AC-13**: MIENTRAS `secrets.hook = "on"` y el hook falta o está desactualizado, o `secrets.ci = "on"` y el workflow falta o está desactualizado, `mth update` DEBE corregirlo como brecha `automatica`.
- **AC-14**: `mth doctor` DEBE marcar ✗ con `secrets.hook = "on"` y `gitleaks` ausente, y ⚠ con el hook o el workflow ausentes o ajenos estando activados, con `secrets.hook` o `secrets.ci` sin decidir, y con `gitleaks` anterior a la versión mínima 8.19.0.
- **AC-15**: `mth survey` DEBE incluir la pregunta `secretos` como `decision` con las opciones `bloquear`, `integrar` y `ninguno`; `mth init --answers` DEBE aplicar sus claves de configuración y un repo nuevo DEBE hacer como mucho seis preguntas.
- **AC-16**: El README, `mth-init` (con el catálogo de preguntas) y `mth-update` DEBEN documentar las claves nuevas, el hook, el workflow, las brechas y que la protección de rama debe exigir la comprobación del workflow.

## Notas

- Tests con un `gitleaks` falso en `PATH`; la plantilla se comprueba sobre su texto, sin dependencias nuevas.
- La sintaxis `git --pre-commit --staged` es la del `.pre-commit-hooks.yaml` oficial de la versión 8.30.1; la versión mínima 8.19.0 es la que sustituye `protect` por `git`.
- Un plugin anterior rechaza las claves nuevas al cargar la configuración ([SPEC-0009](SPEC-0009-actualizacion-del-plugin-con-configuracion-mas-nueva.md), AC-01): actualiza el plugin antes de aceptar las brechas.
- Ni el hook ni el workflow se activan en este repo: la persona decide tras publicar, con `mth update`.
