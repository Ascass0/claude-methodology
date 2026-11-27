# SPEC-0015 · Adopción: deducir, por defecto o preguntar

- Estado: implementada
- Fecha: 2026-11-24
- Formato: compacto
- ADRs: [ADR-0011](../adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md), [ADR-0003](../adr/process/ADR-0003-adopcion-guiada-por-perfiles-de-destino.md)
- Sustituye a: —


## Contexto

- La entrevista de [SPEC-0004](SPEC-0004-adopcion-guiada.md) pregunta todo lo que el perfil y las señales disparan. En una adopción real hizo 12 preguntas en 3 rondas y 8 eran deducibles; ofrecía opciones que fallaban con el inventario y no mostraba el resultado conjunto antes de escribir.
- Decisión: [ADR-0011](../adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md).

## Objetivo

1. Cada pregunta del inventario se resuelve en código como `deducida`, `por_defecto` o `decision`; solo las `decision` se preguntan.
2. Una opción que falla con el inventario no se ofrece.
3. Las preguntas van ordenadas por dependencia y caben en una ronda.
4. La persona ve, antes de que se escriba nada, lo deducido, lo que va por defecto, lo decidido y las capacidades activas y desactivadas.
5. El ADR de adopción registra el resultado de cada pregunta.

## Fuera de alcance

- Detectar otras forjas (GitLab, Bitbucket) y soportarlas: lo hace [SPEC-0016](SPEC-0016-forja-configurable.md) con la clave `forge`, que sustituye a la regla provisional de esta spec.
- Cambiar `mth reconfigure`: sigue mostrando todas las preguntas con su valor actual; solo cambia el orden de las preguntas y desaparece la opción `sustituir`.
- Que `mth` pida la confirmación: la pide la skill `mth-init` ([ADR-0011](../adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md), alternativas).

## Comportamiento

### Resultado de cada pregunta

`mth survey --json` añade a cada pregunta del inventario:

| Campo | Contenido |
|---|---|
| `outcome` | `deducida`, `por_defecto` o `decision` |
| `answer` | Solo si no es `decision`: la respuesta que se aplica (`{"option": …}`), o `null` si el resultado no tiene efecto en la configuración |
| `basis` | Solo si no es `decision`: la evidencia (fichero, rama, remoto) o el motivo del valor por defecto |
| `options` | Solo si el inventario restringe las opciones: las que se ofrecen |

Las preguntas siguen el orden `instrucciones`, `autonomia`, `alcance`, `ramas`, `commits`, `versiones`, `specs`, `decisiones`, `tests`, `revisores`, `colision`, `idioma`, `ci`, `modelos`: primero la precedencia entre el repo y la metodología, después lo que depende de ella.

El inventario añade dos señales: `forge` (`github`, `gitlab` o `none`, deducida del remoto; ver [SPEC-0016](SPEC-0016-forja-configurable.md)) e `integration` (ramas candidatas a integración y cuántas ramas de trabajo salen de ellas).

### Reglas de resolución

| Pregunta | Resultado |
|---|---|
| `alcance` | `deducida`: `gradual`, en los perfiles `existing`, `methodology` y `fork` |
| `ramas` | `deducida` (`usar` la candidata) si hay una única rama candidata (`develop` o `dev`) y todas las ramas de trabajo del remoto, al menos una, salen de ella; `por_defecto` (`crear`) si no hay candidata; `decision` en los demás casos. Una rama sale de la candidata si el punto de bifurcación entre ambas no es ya parte de `main` |
| `commits` | `deducida`: `encadenar`. Solo se ofrece `encadenar` |
| `versiones` | Sin GitHub, con etiquetas con prefijo y sin herramienta de publicación: `deducida` (`continuar`, con los `version_files` detectados); en otro caso, `decision` ([SPEC-0016](SPEC-0016-forja-configurable.md)) |
| `tests` | `deducida` (`comando`) si el inventario detecta `make test` o `just test` (receta llamada exactamente `test` en `Makefile` o `justfile`: `test-all` no cuenta; `make test` primero); en otro caso, `decision` |
| `idioma` | `deducida` si el idioma detectado es `es` o `en`; `por_defecto` (`es`) si es `unknown` |
| `ci` | Si `forge` no es `github`: `deducida` (`sin-ci`) y solo se ofrece `sin-ci`. Con GitHub, `decision` |
| `modelos` | `por_defecto`: `equilibrado` |
| `instrucciones`, `autonomia`, `specs`, `decisiones`, `revisores`, `colision`, `secretos` | `decision` ([SPEC-0024](SPEC-0024-hook-de-precommit-y-workflow-de-ci-para-secretos.md)) |

`ci` se pregunta también cuando `forge` no es `github`, aunque haya workflows, para que el resultado conste.

Si `forge` no es `github`, no se ofrece `ci: crear` (crea un workflow de GitHub Actions). Si no hay candidata a integración, no se ofrece `ramas: usar`.

### Respuestas: `mth init --answers`

- Exige respuesta solo a las preguntas `decision`. A las demás se les aplica su `answer`; una respuesta explícita la sustituye y el ADR la registra como `decision`.
- Rechaza, sin modificar nada, una respuesta a una pregunta que no está en el inventario y una opción que el inventario no ofrece.
- La opción `commits: sustituir` desaparece: un hook ajeno solo se encadena. `hooks.commit_msg = replace` sigue siendo un valor válido de la configuración ([SPEC-0006](SPEC-0006-hooks-commit-msg-encadenados.md)), pero la entrevista no lo ofrece.
- `revisores: agentes` admite `paths`: una tabla `{agente: [globs]}` que va a `[review.paths]` de la configuración. Sirve para los revisores del repo que solo aplican a un área.

### Resumen previo

`mth init --answers FICHERO` imprime un plan antes de escribir, y `--plan` lo imprime sin escribir nada (valida las respuestas y la configuración como la adopción, y termina). Cuatro bloques:

1. **Deducido**: cada pregunta, su valor y su evidencia.
2. **Por defecto**: cada pregunta y su valor; se cambia con `mth reconfigure`.
3. **Decidido**: cada pregunta, la opción elegida y su efecto.
4. **Capacidades**: activas y desactivadas, cada una con su motivo. Son: `mth integrate`, `mth release` (con otra forja, solo su parte local; [SPEC-0016](SPEC-0016-forja-configurable.md)), CI exigida para integrar (`ci.required`), tests antes de integrar (`commands.test`), validación de mensajes de commit y agentes del catálogo.

### ADR de adopción

La tabla del ADR de adopción tiene una columna **Resultado** (`deducida`, `por_defecto` o `decision`) y, en las preguntas no decididas, la evidencia en la columna de nota.

### Skill `mth-init`

- Pregunta solo las preguntas `decision`, en su orden, en una sola ronda con `AskUserQuestion` y ofreciendo solo las `options` del inventario. Si hay más de cuatro, las hace y avisa de que falta una regla de deducción.
- Antes de adoptar: escribe el JSON, ejecuta `mth init --answers FICHERO --plan`, presenta el resumen y pide confirmación. Solo después ejecuta la adopción. Si la persona corrige un valor, añade esa respuesta y vuelve a mostrar el resumen.
- El catálogo de preguntas solo describe comportamiento que existe.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Opción no ofrecida por el inventario (p. ej. `ci: crear` sin GitHub) | `mth init --answers`: error con la pregunta y las opciones ofrecidas; no se modifica nada | AC-04, AC-07 |
| FM-02 | Respuesta a una pregunta que no está en el inventario | Error; no se modifica nada | AC-07 |
| FM-03 | `review.paths` con un agente que no está en `agents`, que no es una lista de textos o que está vacía | Error de validación de las respuestas o de la configuración; no se modifica nada | AC-10 |
| FM-04 | Señal de ramas ilegible (`merge-base` falla) | `mth survey`: la rama no cuenta como salida de la candidata y la pregunta pasa a `decision` | AC-02 |
| FM-05 | Más ramas de trabajo que el límite del inventario (50), o un error de git distinto de «no es ancestro» al comprobar una bifurcación | Solo se examinan las 50 primeras y `working` es el total real; la regla no se confirma y `ramas` pasa a `decision`; una comprobación fallida no cuenta como «sale de la candidata» | AC-02 |
| FM-06 | `--plan` sin `--answers` | `mth init`: error de uso | AC-08 |

## Criterios de aceptación

- **AC-01**: CUANDO se ejecuta `mth survey --json`, `mth` DEBE dar a cada pregunta un `outcome` entre `deducida`, `por_defecto` y `decision`, con `answer` y `basis` en las no decididas, y `asked()` DEBE devolver solo las `decision` en el orden de dependencia (`instrucciones` y `autonomia` primero).
- **AC-02**: `ramas` DEBE ser `deducida` con una única candidata de la que salen todas las ramas de trabajo, `por_defecto` (`crear`) sin candidata y `decision` con varias candidatas o sin ramas de trabajo que la confirmen.
- **AC-03**: SI hay un hook `commit-msg` ajeno, ENTONCES `commits` DEBE ser `deducida` (`encadenar`), solo DEBE ofrecerse `encadenar` y `sustituir` DEBE rechazarse.
- **AC-04**: SI la forja no es GitHub, ENTONCES `ci` DEBE ser `deducida` (`sin-ci`) y `ci: crear` DEBE rechazarse; con GitHub DEBE preguntarse. La deducción de `versiones` sin GitHub la fija [SPEC-0016](SPEC-0016-forja-configurable.md).
- **AC-05**: `tests` DEBE ser `deducida` con un objetivo `test` en `Makefile` o `justfile` aunque haya más candidatos, y `decision` si no.
- **AC-06**: `idioma` DEBE ser `deducida` con idioma detectado (`es` o `en`) y `por_defecto` (`es`) con `unknown`; `modelos` DEBE ser `por_defecto`; `alcance` DEBE ser `deducida` (`gradual`) en `existing`, `methodology` y `fork`.
- **AC-07**: `mth init --answers` DEBE exigir respuesta solo a las `decision`, aplicar el valor de las demás, dejar que una respuesta explícita lo sustituya y rechazar una opción no ofrecida o una pregunta fuera del inventario.
- **AC-08**: CUANDO se ejecuta `mth init --answers --plan`, `mth` DEBE imprimir los cuatro bloques (deducido con evidencia, por defecto, decidido, capacidades activas y desactivadas con motivo) sin escribir nada; la adopción DEBE imprimir el mismo plan antes de escribir.
- **AC-09**: La tabla del ADR de adopción DEBE tener, por cada pregunta del inventario, su resultado (`deducida`, `por_defecto` o `decision`).
- **AC-10**: Todas las opciones del catálogo de preguntas DEBEN existir en `mth init --answers` y aplicarse a la configuración; todos los comandos `mth` y claves de configuración que nombran sus textos DEBEN existir; `revisores` DEBE aceptar `paths` y escribirlo en `[review.paths]`, que el cálculo de revisores obligatorios respeta.
- **AC-11**: DADO el inventario del caso real (remoto en GitLab, única rama `dev` de la que salen las demás, hook `commit-msg` ajeno, `Makefile` con `test` y `pytest`, docs en español, 42 ADR, `CLAUDE.md`), la entrevista DEBE tener como máximo 5 preguntas `decision` (con `secretos`; más de cuatro van en dos rondas, por el límite de `AskUserQuestion`), el plan de adopción DEBE listar `mth integrate` y `mth release` como desactivadas y la skill DEBE documentar una sola ronda (dos si hay más de cuatro preguntas) y el resumen antes de escribir.

## Notas

Modifica la entrevista de [SPEC-0004](SPEC-0004-adopcion-guiada.md): «solo las preguntas que el inventario pide» pasa a «solo las que son `decision`», y la opción `commits: sustituir` ya no existe.
