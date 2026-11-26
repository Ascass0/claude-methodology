# SPEC-0001 · Delegación verificable: plan de trabajo, manifiestos y agentes que fallan

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: ADR-0001
- Sustituye a: —


## Contexto

- `mth-develop` permite dividir una spec en tareas con ficheros disjuntos y delegarlas en agentes `dev-*`, que devuelven un manifiesto en prosa: todo ello es criterio, no mecanismo.
- El alcance de cada tarea es texto: nada detecta que un agente edite otros ficheros ni que dos tareas paralelas se pisen.
- El manifiesto no se valida: un agente caído, sin tiempo o incompleto puede pasar por tarea terminada.
- Lo mismo con los revisores: `mth review record` aceptaba el número de bloqueantes que escribía la sesión principal, también de un revisor que no terminó.
- PRINCIPLES §2 (determinismo): lo comprobable lo comprueba código.
- Inspiración: el estándar de *implementation readiness* de [elephant-goldfish-model](https://github.com/google/elephant-goldfish-model): lista cerrada de ficheros por tarea, fases que dejan el repo estable, retornos estructurados.

## Objetivo

Al delegar la sesión principal:

1. El reparto es un **plan de trabajo** en la spec, validado por `mth` antes de lanzar nada: tareas, oleadas, ficheros permitidos y criterios, sin solapamientos en una oleada.
2. Cada agente devuelve un **manifiesto JSON** que `mth` contrasta con el plan y los cambios reales antes de aceptar la oleada.
3. Un agente (implementador o revisor) que no termina nunca cuenta como trabajo hecho ni como revisión aprobada.

## Fuera de alcance

- Aislar las tareas paralelas en worktrees: comparten árbol de trabajo. La verificación se hace al cerrar la oleada.
- Lanzar o relanzar agentes desde `mth`: lo hace la sesión principal, siguiendo la skill.
- Revisar la spec y el plan con contexto limpio antes de aprobarlos, clasificar los hallazgos al resolver e informes de deriva: specs futuras.
- Guardar el resultado de `mth plan verify` como gate de `mth integrate`.
- Validar con JSON Schema: la validación es propia, estricta y sin dependencias.

## Comportamiento

### Plan de trabajo

Sección opcional de la spec. Solo es obligatoria cuando la sesión principal delega al menos dos tareas; si implementa ella misma, no hace falta. Formato ([ADR-0001](../adr/process/ADR-0001-plan-y-manifiesto-verificados.md)):

```markdown
## Plan de trabajo

| Tarea | Oleada | Ficheros | Criterios |
|---|---|---|---|
| T-01 | 1 | `src/parser.py`, `tests/test_parser.py` | AC-01, AC-02 |
| T-02 | 1 | `src/render/**`, `tests/test_render.py` | AC-03 |
| T-03 | 2 | `src/cli.py`, `tests/test_cli.py` | AC-04 |
```

Reglas:

- La sección es un encabezado de nivel 2 exactamente `## Plan de trabajo`, fuera de bloques de código. Termina en el siguiente encabezado de nivel 1 o 2.
- La cabecera de la tabla tiene exactamente las columnas `Tarea | Oleada | Ficheros | Criterios`, en ese orden. La tabla es la primera de la sección.
- `Tarea`: `T-NN` (dos dígitos), única en la spec.
- `Oleada`: entero ≥ 1. Las tareas de una oleada se ejecutan en paralelo; una oleada empieza cuando la anterior está verificada y confirmada.
- `Ficheros`: uno o más elementos entre comillas invertidas, separados por comas. Cada uno es una ruta relativa a la raíz del repo o un glob (`*`, `**`, `?`) para ficheros cuyo nombre no se conoce de antemano. Nada de rutas absolutas, con `..` ni sin normalizar (`./a`, `a//b`, `a/`): se rechazan en vez de normalizarse, porque dos formas de escribir un mismo fichero burlarían la comprobación de solapamiento.
- `Criterios`: uno o más `AC-NN` separados por comas, todos declarados en la propia spec.
- Cada criterio de la spec está asignado al menos a una tarea.
- Dos tareas de la misma oleada no comparten ficheros. Entre globs la comprobación es conservadora (fail-safe): se consideran solapados salvo que sus prefijos literales (hasta el primer comodín) no puedan coincidir.
- Como máximo 50 tareas.

`mth plan check SPEC-NNNN` valida el plan, informa de todos los errores a la vez (con su línea) y, si es válido, lista las tareas por oleada. `mth trace` aplica las mismas comprobaciones a toda spec que tenga la sección.

### Manifiesto de tarea

El agente lo devuelve al terminar. La sesión principal lo guarda tal cual en un fichero (fuera del repo) y no lo reescribe.

```json
{
  "task": "T-01",
  "status": "done",
  "files": ["src/parser.py", "tests/test_parser.py"],
  "criteria": ["AC-01", "AC-02"],
  "tests": [{"name": "tests/test_parser.py::test_rejects_empty", "result": "pass"}],
  "decisions": ["…"],
  "deviations": [],
  "questions": []
}
```

- Todos los campos son obligatorios y no se admiten campos desconocidos.
- `status`: `done`, `blocked` (necesita una decisión) o `failed`.
- `files`: ficheros creados, modificados o borrados (rutas relativas).
- `tests[].result`: `pass` o `fail`.
- `decisions`, `deviations` y `questions`: listas de cadenas.
- Tamaño máximo: 256 KiB.

### Verificación de una oleada

`mth plan verify SPEC-NNNN --wave N --manifest <fichero> [--manifest <fichero> …]` se ejecuta con los cambios de la oleada sin confirmar (las oleadas anteriores, ya confirmadas). Acepta la oleada solo si:

- el plan es válido y la oleada existe;
- cada manifiesto es válido, pertenece a una tarea de esa oleada y no hay dos manifiestos de la misma tarea;
- cada tarea de la oleada tiene manifiesto: sin él, la tarea está **no ejecutada**;
- cada manifiesto tiene `status: done` (si no, la tarea está **no completada**); `done` es incompatible con `questions` no vacío;
- el manifiesto cubre todos los criterios de su tarea y solo esos;
- informa al menos de un test y ninguno ha fallado;
- todo fichero del manifiesto está dentro de los permitidos de su tarea y tiene cambios reales;
- todo cambio del árbol de trabajo (respecto a HEAD, incluidos los ficheros nuevos no ignorados) lo declara algún manifiesto de la oleada.

Informa de todos los problemas a la vez y termina con error si hay alguno. Los `deviations` no vacíos se muestran como avisos (⚠): no bloquean, pero la skill exige resolverlos (corrigiendo la spec si procede) antes de confirmar.

### Agentes que fallan

- **Implementadores:** una tarea no ejecutada o no completada se relanza una sola vez. Si vuelve a fallar, la sesión principal la implementa ella misma o rehace el plan (corrigiendo la spec en un commit), y lo deja anotado en el PR. Nunca se edita un manifiesto para que pase la verificación.
- **Revisores:** `mth review record <agente> --report <fichero> --summary "…"` toma el número de bloqueantes de la última línea no vacía del informe del revisor, que debe ser `BLOQUEANTES: <n>` (desde [SPEC-0013](SPEC-0013-registro-de-revisiones-calculado-por-mth.md), `mth` lo calcula contando los hallazgos `[bloqueante]` y contrasta esa línea; un informe que falla se registra como fallido en lugar de no registrarse). Un informe que no existe, está vacío, supera 256 KiB o no termina en esa línea es un revisor **no ejecutado**: se registra como fallido, no aprueba nada y la revisión sigue sin cumplirse. La sesión principal lo relanza una vez; si vuelve a fallar, se aplica la regla de los tres fallos (PRINCIPLES §11). El número de bloqueantes ya no se escribe a mano (`--blocking` desaparece).

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Plan mal formado (cabecera, ID, oleada, ficheros vacíos, ruta fuera del repo, más de 50 tareas) | `mth plan check` / `mth trace`: error con su línea; no se delega nada | AC-02 |
| FM-02 | Dos tareas de una oleada pueden tocar el mismo fichero | `mth plan check`: error que nombra ambas; con duda entre globs, solapamiento | AC-03 |
| FM-03 | Criterio inexistente o criterio de la spec sin tarea | `mth plan check`: error | AC-04 |
| FM-04 | Spec sin plan o ID no definido en `plan verify` | Error; nada que verificar | AC-06 |
| FM-05 | Agente caído, sin respuesta o fuera de tiempo (sin manifiesto) | Tarea «no ejecutada»; la oleada no se acepta | AC-07 |
| FM-06 | Manifiesto ilegible: JSON inválido, campos que faltan o sobran, tipos erróneos, más de 256 KiB, tarea ajena a la oleada o duplicada | Error; la tarea cuenta como no ejecutada | AC-08 |
| FM-07 | Agente bloqueado o fallido (`blocked`, `failed`, preguntas abiertas) | Tarea «no completada»; la oleada no se acepta | AC-07, AC-10 |
| FM-08 | El agente tocó ficheros fuera de su alcance o hay cambios sin declarar | Error con cada fichero | AC-09 |
| FM-09 | El manifiesto afirma cambios que no existen | Error (afirmación falsa) | AC-09 |
| FM-10 | Criterios sin cubrir, tests en rojo o sin tests | Error | AC-10 |
| FM-11 | Revisor caído o informe sin la línea `BLOQUEANTES: <n>` | `mth review record`: registro fallido (SPEC-0013); la revisión no aprueba y `mth integrate` la rechaza | AC-12 |

## Criterios de aceptación

- **AC-01**: CUANDO se ejecuta `mth plan check` sobre un plan válido, `mth` DEBE aceptarlo y listar sus tareas agrupadas por oleada.
- **AC-02**: SI el plan está mal formado (cabecera distinta, ID de tarea inválido o repetido, oleada no entera o menor que 1, celda de ficheros vacía o con texto fuera de las comillas invertidas, ruta absoluta, con `..` o sin normalizar, más de 50 tareas), ENTONCES `mth plan check` DEBE rechazarlo indicando la línea.
- **AC-03**: SI dos tareas de la misma oleada comparten un fichero (por ruta exacta, por un glob que cubre una ruta o por dos globs con prefijos compatibles), ENTONCES `mth plan check` DEBE rechazarlo; DEBE aceptar el mismo fichero en oleadas distintas.
- **AC-04**: SI el plan cita un criterio que la spec no declara o un criterio de la spec no tiene tarea asignada, ENTONCES `mth plan check` DEBE rechazarlo.
- **AC-05**: CUANDO una spec tiene la sección `Plan de trabajo`, `mth trace` DEBE informar de los errores de su plan; NO DEBE decir nada de las specs sin ella.
- **AC-06**: CUANDO los manifiestos son válidos, están completos y coinciden con los cambios del árbol de trabajo, `mth plan verify` DEBE aceptar la oleada.
- **AC-07**: SI una tarea de la oleada no tiene manifiesto o su `status` no es `done`, ENTONCES `mth plan verify` DEBE marcarla como «no ejecutada» o «no completada» respectivamente y rechazar la oleada.
- **AC-08**: SI un manifiesto tiene JSON inválido, campos que faltan o sobran, tipos o valores no permitidos, más de 256 KiB, o es de una tarea ajena a la oleada o duplicado, ENTONCES `mth plan verify` DEBE rechazarlo.
- **AC-09**: SI un manifiesto declara un fichero fuera de los permitidos de su tarea, un cambio del árbol de trabajo no está declarado por ningún manifiesto o un fichero declarado no tiene cambios reales, ENTONCES `mth plan verify` DEBE rechazar la oleada.
- **AC-10**: SI un manifiesto `done` no cubre todos los criterios de su tarea, declara otros, no tiene tests, tiene algún test en rojo o preguntas abiertas, ENTONCES `mth plan verify` DEBE rechazarlo.
- **AC-11**: CUANDO un manifiesto trae `deviations`, `mth plan verify` DEBE mostrarlas como avisos y NO DEBE rechazar la oleada por ellas.
- **AC-12**: SI el informe de un revisor no existe, está vacío, supera 256 KiB o no termina en `BLOQUEANTES: <n>`, ENTONCES `mth review record` NO DEBE registrar la revisión como aprobada; CUANDO es válido, DEBE tomar los bloqueantes de esa última línea.

## Notas

Esta spec no lleva plan de trabajo: la implementa la sesión principal sin delegar.
