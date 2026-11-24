# SPEC-0015 · Adopción: deducir, por defecto o preguntar

- Estado: implementada
- Fecha: 2026-11-24
- ADRs: [ADR-0011](../adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md), [ADR-0003](../adr/process/ADR-0003-adopcion-guiada-por-perfiles-de-destino.md)
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0015/AC-NN`. -->

## Contexto

La entrevista de [SPEC-0004](SPEC-0004-adopcion-guiada.md) pregunta todo lo que el perfil y las señales disparan. En una adopción real hizo 12 preguntas en 3 rondas y 8 eran deducibles; ofrecía opciones que fallaban con el inventario y no mostraba el resultado conjunto antes de escribir. [ADR-0011](../adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md) recoge la decisión.

## Objetivo

1. Cada pregunta del inventario se resuelve en código como `deducida`, `por_defecto` o `decision`; solo las `decision` se preguntan.
2. Una opción que falla con el inventario no se ofrece.
3. Las preguntas van ordenadas por dependencia y caben en una ronda.
4. La persona ve, antes de que se escriba nada, lo deducido, lo que va por defecto, lo decidido y las capacidades activas y desactivadas.
5. El ADR de adopción registra el resultado de cada pregunta.

## Fuera de alcance

- Detectar otras forjas (GitLab, Bitbucket) y soportarlas: lo hará el ADR de `forge`. Aquí, todo remoto que no sea `github.com` cuenta como «no GitHub».
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

El inventario añade dos señales: `forge` (`github` si el remoto está en `github.com`, `other` en otro caso) e `integration` (ramas candidatas a integración y cuántas ramas de trabajo salen de ellas).

### Reglas de resolución

| Pregunta | Resultado |
|---|---|
| `alcance` | `deducida`: `gradual`, en los perfiles `existing`, `methodology` y `fork` |
| `ramas` | `deducida` (`usar` la candidata) si hay una única rama candidata (`develop` o `dev`) y todas las ramas de trabajo del remoto, al menos una, salen de ella; `por_defecto` (`crear`) si no hay candidata; `decision` en los demás casos. Una rama sale de la candidata si el punto de bifurcación entre ambas no es ya parte de `main` |
| `commits` | `deducida`: `encadenar`. Solo se ofrece `encadenar` |
| `versiones` | Si `forge` es `other`: `deducida` sin efecto en la configuración (`answer` nulo): `mth release` no está disponible. Con GitHub, `decision` |
| `tests` | `deducida` (`comando`) si el inventario detecta `make test` o `just test` (objetivo `test` de `Makefile` o `justfile`; `make test` primero); en otro caso, `decision` |
| `idioma` | `deducida` si el idioma detectado es `es` o `en`; `por_defecto` (`es`) si es `unknown` |
| `ci` | Si `forge` es `other`: `deducida` (`sin-ci`) y solo se ofrece `sin-ci`. Con GitHub, `decision` |
| `modelos` | `por_defecto`: `equilibrado` |
| `instrucciones`, `autonomia`, `specs`, `decisiones`, `revisores`, `colision` | `decision` |

`ci` se pregunta también cuando `forge` es `other`, aunque haya workflows, para que el resultado conste.

Si `forge` es `other`, no se ofrecen `versiones: continuar` ni `prefijo` (usan `mth release`) ni `ci: crear` (crea un workflow de GitHub Actions). Si no hay candidata a integración, no se ofrece `ramas: usar`.

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
4. **Capacidades**: activas y desactivadas, cada una con su motivo. Son: `mth integrate`, `mth release` (ambas necesitan GitHub), CI exigida para integrar (`ci.required`), tests antes de integrar (`commands.test`), validación de mensajes de commit y agentes del catálogo.

### ADR de adopción

La tabla del ADR de adopción tiene una columna **Resultado** (`deducida`, `por_defecto` o `decision`) y, en las preguntas no decididas, la evidencia en la columna de nota.

### Skill `mth-init`

- Pregunta solo las preguntas `decision`, en su orden, en una sola ronda con `AskUserQuestion` y ofreciendo solo las `options` del inventario. Si hay más de cuatro, las hace y avisa de que falta una regla de deducción.
- Antes de adoptar: escribe el JSON, ejecuta `mth init --answers FICHERO --plan`, presenta el resumen y pide confirmación. Solo después ejecuta la adopción. Si la persona corrige un valor, añade esa respuesta y vuelve a mostrar el resumen.
- El catálogo de preguntas solo describe comportamiento que existe.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Opción no ofrecida por el inventario (por ejemplo, `ci: crear` sin GitHub) | `mth init --answers` | Error con la pregunta y las opciones ofrecidas; no se modifica nada |
| Respuesta a una pregunta que no está en el inventario | `mth init --answers` | Error; no se modifica nada |
| `review.paths` con un agente que no es revisor, o con globs vacíos | `mth init --answers` | Error de validación de la configuración; no se modifica nada |
| Señal de ramas ilegible (`merge-base` falla) | `mth survey` | La rama no cuenta como salida de la candidata: la pregunta pasa a `decision` |
| Más ramas de trabajo que el límite de inventario (50), o un error de git distinto de «no es ancestro» al comprobar una bifurcación | `mth survey` | Solo se examinan las 50 primeras y `working` es el total real; la regla no se confirma y `ramas` pasa a `decision`. Una comprobación fallida no cuenta como «sale de la candidata» |
| `--plan` sin `--answers` | `mth init` | Error de uso |

## Criterios de aceptación

- **AC-01**: `mth survey --json` da a cada pregunta un `outcome` entre `deducida`, `por_defecto` y `decision`, con `answer` y `basis` en las no decididas, y `asked()` devuelve solo las `decision`, en el orden de dependencia (`instrucciones` y `autonomia` primero).
- **AC-02**: `ramas` es `deducida` con una única candidata de la que salen todas las ramas de trabajo, `por_defecto` (`crear`) sin candidata y `decision` con varias candidatas o sin ramas de trabajo que la confirmen.
- **AC-03**: Con un hook `commit-msg` ajeno, `commits` es `deducida` (`encadenar`), solo se ofrece `encadenar` y `sustituir` se rechaza.
- **AC-04**: Con un remoto que no es GitHub, `ci` es `deducida` (`sin-ci`), `versiones` es `deducida` sin efecto, y `versiones: continuar`, `versiones: prefijo` y `ci: crear` se rechazan; con GitHub se preguntan.
- **AC-05**: `tests` es `deducida` con un objetivo `test` en `Makefile` o `justfile` aunque haya más candidatos, y `decision` si no.
- **AC-06**: `idioma` es `deducida` con idioma detectado (`es` o `en`) y `por_defecto` (`es`) con `unknown`; `modelos` es `por_defecto`; `alcance` es `deducida` (`gradual`) en `existing`, `methodology` y `fork`.
- **AC-07**: `mth init --answers` exige respuesta solo a las `decision`, aplica el valor de las demás, deja que una respuesta explícita lo sustituya y rechaza una opción no ofrecida o una pregunta fuera del inventario.
- **AC-08**: `mth init --answers --plan` imprime los cuatro bloques (deducido con evidencia, por defecto, decidido, capacidades activas y desactivadas con motivo) sin escribir nada, y la adopción imprime el mismo plan antes de escribir.
- **AC-09**: La tabla del ADR de adopción tiene, por cada pregunta del inventario, su resultado (`deducida`, `por_defecto` o `decision`).
- **AC-10**: Todas las opciones del catálogo de preguntas existen en `mth init --answers` y se aplican a la configuración, todos los comandos `mth` y todas las claves de configuración que nombran sus textos existen, y `revisores` acepta `paths` y lo escribe en `[review.paths]`, que el cálculo de revisores obligatorios respeta.
- **AC-11**: Con el inventario del caso real (remoto en GitLab, única rama `dev` de la que salen las demás, hook `commit-msg` ajeno, `Makefile` con `test` y `pytest`, docs en español, 42 ADR, `CLAUDE.md`), la entrevista tiene como máximo 4 preguntas `decision`, la adopción con las respuestas de la persona genera un plan que lista `mth integrate` y `mth release` como desactivadas, y la skill documenta una sola ronda y el resumen antes de escribir.

## Notas

Modifica la entrevista de [SPEC-0004](SPEC-0004-adopcion-guiada.md): «solo las preguntas que el inventario pide» pasa a «solo las que son `decision`», y la opción `commits: sustituir` ya no existe.
