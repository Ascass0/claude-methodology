# SPEC-0001 · Delegación verificable: plan de trabajo, manifiestos y agentes que fallan

- Estado: aprobada
- Fecha: 2026-11-18
- ADRs: ADR-0001
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0001/AC-NN`. -->

## Contexto

`mth-develop` permite a la sesión principal dividir una spec en tareas con ficheros disjuntos y delegarlas en los agentes `dev-*`, que devuelven un manifiesto en prosa. Todo eso es criterio, no mecanismo:

- el alcance de cada tarea ("puede tocar X") es texto: nada detecta que un agente edite otros ficheros ni que dos tareas paralelas se pisen;
- el manifiesto no se puede validar: un agente que se cae, agota el tiempo o devuelve algo incompleto puede pasar por una tarea terminada;
- lo mismo ocurre con los revisores: `mth review record` acepta el número de bloqueantes que escribe la sesión principal, también para un revisor que no llegó a terminar.

El principio de determinismo (PRINCIPLES §2) exige que lo comprobable lo compruebe código. La idea se inspira en el estándar de *implementation readiness* de [elephant-goldfish-model](https://github.com/google/elephant-goldfish-model): una lista cerrada de ficheros por tarea, fases que dejan el repo estable y retornos estructurados de los workers.

## Objetivo

Cuando la sesión principal delega:

1. el reparto de trabajo es un **plan de trabajo** en la spec, validado por `mth` antes de lanzar nada: tareas, oleadas, ficheros permitidos y criterios, sin solapamientos dentro de una oleada;
2. cada agente devuelve un **manifiesto JSON** que `mth` contrasta con el plan y con los cambios reales antes de aceptar la oleada;
3. un agente (implementador o revisor) que no termina nunca cuenta como trabajo hecho ni como revisión aprobada.

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
- `Ficheros`: uno o más elementos entre comillas invertidas, separados por comas. Cada uno es una ruta relativa a la raíz del repo o un glob (`*`, `**`, `?`) para ficheros cuyo nombre no se conoce de antemano. Nada de rutas absolutas ni `..`.
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
- **Revisores:** `mth review record <agente> --report <fichero> --summary "…"` toma el número de bloqueantes de la última línea no vacía del informe del revisor, que debe ser `BLOQUEANTES: <n>`. Un informe que no existe, está vacío, supera 256 KiB o no termina en esa línea es un revisor **no ejecutado**: no se registra nada y la revisión sigue pendiente. La sesión principal lo relanza una vez; si vuelve a fallar, se aplica la regla de los tres fallos (PRINCIPLES §11). El número de bloqueantes ya no se escribe a mano (`--blocking` desaparece).

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Plan mal formado (cabecera, ID, oleada, ficheros vacíos, ruta fuera del repo, más de 50 tareas) | `mth plan check` / `mth trace` | Error con su línea; no se delega nada |
| Dos tareas de la misma oleada pueden tocar el mismo fichero | `mth plan check` | Error que nombra ambas tareas; en caso de duda entre globs, se considera solapamiento |
| Criterio inexistente o criterio de la spec sin tarea | `mth plan check` | Error |
| Spec sin plan o ID no definido en `plan verify` | `mth plan verify` | Error; nada que verificar |
| Agente caído, sin respuesta o fuera de tiempo (sin manifiesto) | `mth plan verify` | Tarea "no ejecutada"; la oleada no se acepta |
| Manifiesto ilegible: JSON inválido, campos que faltan o sobran, tipos erróneos, más de 256 KiB, tarea ajena a la oleada o duplicada | `mth plan verify` | Error; la tarea cuenta como no ejecutada |
| Agente bloqueado o fallido (`blocked`, `failed`, preguntas abiertas) | `mth plan verify` | Tarea "no completada"; la oleada no se acepta |
| El agente tocó ficheros fuera de su alcance o hay cambios que nadie declara | `mth plan verify` | Error con cada fichero |
| El manifiesto afirma cambios que no existen | `mth plan verify` | Error (afirmación falsa) |
| Criterios sin cubrir, tests en rojo o sin tests | `mth plan verify` | Error |
| Revisor caído o informe sin la línea `BLOQUEANTES: <n>` | `mth review record` | No se registra; la revisión sigue pendiente y `mth integrate` la exige |

## Criterios de aceptación

- **AC-01**: `mth plan check` acepta un plan válido y lista sus tareas agrupadas por oleada.
- **AC-02**: `mth plan check` rechaza, con su línea, un plan mal formado: cabecera distinta, tarea con ID inválido o repetido, oleada no entera o menor que 1, celda de ficheros vacía o con texto fuera de las comillas invertidas, ruta absoluta o con `..`, y más de 50 tareas.
- **AC-03**: `mth plan check` rechaza dos tareas de la misma oleada que comparten un fichero, por ruta exacta, por un glob que cubre una ruta o por dos globs con prefijos compatibles, y acepta el mismo fichero en oleadas distintas.
- **AC-04**: `mth plan check` rechaza un criterio que la spec no declara y un criterio de la spec que ninguna tarea tiene asignado.
- **AC-05**: `mth trace` informa de los errores del plan de cualquier spec que tenga la sección `Plan de trabajo` y no dice nada de las specs sin ella.
- **AC-06**: `mth plan verify` acepta una oleada cuyos manifiestos son válidos, están completos y coinciden con los cambios del árbol de trabajo.
- **AC-07**: `mth plan verify` marca como "no ejecutada" una tarea de la oleada sin manifiesto y como "no completada" una con `status` distinto de `done`, y rechaza la oleada.
- **AC-08**: `mth plan verify` rechaza un manifiesto con JSON inválido, con campos que faltan o sobran, con tipos o valores no permitidos, de más de 256 KiB, de una tarea que no pertenece a la oleada o duplicado.
- **AC-09**: `mth plan verify` rechaza un fichero declarado fuera de los permitidos de su tarea, un cambio del árbol de trabajo que ningún manifiesto declara y un fichero declarado sin cambios reales.
- **AC-10**: `mth plan verify` rechaza un manifiesto `done` que no cubre todos los criterios de su tarea o declara otros, sin tests, con algún test en rojo o con preguntas abiertas.
- **AC-11**: `mth plan verify` muestra los `deviations` como avisos y no rechaza la oleada por ellos.
- **AC-12**: `mth review record` toma los bloqueantes de la última línea `BLOQUEANTES: <n>` del informe, y no registra nada (la revisión sigue pendiente) cuando el informe no existe, está vacío, supera 256 KiB o no termina en esa línea.

## Notas

Esta spec no lleva plan de trabajo: la implementa la sesión principal sin delegar.
