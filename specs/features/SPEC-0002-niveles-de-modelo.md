# SPEC-0002 · Niveles de modelo por tarea, escalado en el reintento y métricas

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: ADR-0002
- Sustituye a: —


## Contexto

- Con [SPEC-0001](SPEC-0001-delegacion-verificable.md) la sesión principal reparte el trabajo en un plan y verifica cada oleada; todas las tareas se delegan con el modelo de la sesión principal aunque su dificultad difiera mucho.
- Precios de la API por millón de tokens (entrada/salida): Opus 4/20 $, Sonnet 2/10 $, Haiku 0,10/0,50 $; una tarea mecánica con Opus cuesta unas 40 veces lo que con Haiku.
- Que un modelo barato falle es aceptable: `mth plan verify` lo detecta.
- Falta decidir el modelo de cada tarea al planificar (cuando mejor se conoce su dificultad), no repetir un intento fallido con el mismo modelo, y tener datos por nivel en lugar de ajustar a ojo (PRINCIPLES §2).

## Objetivo

1. Cada tarea del plan tiene un **nivel de modelo**, declarado en el plan o tomado de la configuración.
2. El reintento de una tarea fallida usa el **nivel siguiente** de una escalera configurable.
3. Cada verificación de oleada deja constancia del modelo y resultado de cada tarea, y `mth` resume las métricas por nivel.

## Fuera de alcance

- Lanzar agentes: lo hace la sesión principal con la herramienta Agent de Claude Code, pasando el alias que da `mth`.
- El nivel de esfuerzo (`effort`) por tarea.
- Elegir modelo para la sesión principal: la elige quien la abre.
- Cambiar los modelos automáticamente según las métricas: `mth` informa y la sesión principal o la persona deciden.
- Compartir métricas entre máquinas: viven en `.git/mth/trace.jsonl`, que es local.

## Comportamiento

### Configuración

Tabla nueva `[models]` en `.claude/methodology.toml` ([ADR-0002](../adr/process/ADR-0002-niveles-de-modelo.md)):

```toml
[models]
ladder = ["haiku", "sonnet", "opus"]  # escalera de reintento, de menor a mayor
task = "sonnet"                       # nivel de una tarea del plan que no declara modelo
review = "sonnet"                     # revisores (verificador y los del repo)
documenter = "sonnet"                 # rol documenter
```

- Los valores son alias de modelo de la herramienta Agent de Claude Code: `haiku`, `sonnet`, `opus` o `fable`.
- `ladder` no puede estar vacía ni repetir alias. `task`, `review` y `documenter` deben estar en `ladder`.
- Sin tabla `[models]` se aplican los valores por defecto de arriba. Una configuración inválida es fail-fast: ningún comando se ejecuta.
- `mth models` muestra la escalera y el nivel de cada rol.

### Columna `Modelo` en el plan

El plan de trabajo admite una quinta columna opcional, `Modelo`, al final:

```markdown
| Tarea | Oleada | Ficheros | Criterios | Modelo |
|---|---|---|---|---|
| T-01 | 1 | `src/parser.py`, `tests/test_parser.py` | AC-01 | haiku |
| T-02 | 1 | `src/render/**` | AC-02 | |
```

- La cabecera es la de [SPEC-0001](SPEC-0001-delegacion-verificable.md) o esa misma con `Modelo` al final.
- Una celda vacía toma `models.task`. Un valor que no está en `ladder` es un error del plan, con su línea.
- `mth plan check` muestra el nivel efectivo de cada tarea: `Oleada 1: T-01 (haiku), T-02 (sonnet)`.

### Modelo de cada intento

`mth plan model SPEC-NNNN T-NN [--retry]` escribe en la salida estándar solo el alias que hay que pasar a la herramienta Agent:

- sin `--retry`, el nivel efectivo de la tarea;
- con `--retry`, el siguiente nivel de `ladder`. Si ya está en el último, repite ese nivel.

La skill `mth-develop` lanza el primer intento con el primero y el único reintento con el segundo.

### Registro y métricas

- `mth plan verify` acepta `--model T-NN=<alias>` (repetible) para indicar el modelo con el que se ejecutó cada tarea. Si una tarea no lo indica, se registra su nivel efectivo. Un alias que no está en `ladder`, o una tarea que no pertenece a la oleada, es un error: no se verifica nada.
- Por cada tarea de la oleada, `mth plan verify` añade a `.git/mth/trace.jsonl` un evento `plan.task` con la spec, la tarea, la oleada, el modelo, el resultado y la huella SHA-256 de su manifiesto (vacía si no hay). Lo hace también cuando rechaza la oleada.
- Resultado de cada tarea:
  - `ok`: sin errores propios;
  - `not_run`: sin manifiesto válido;
  - `not_completed`: `status` distinto de `done`;
  - `rejected`: cualquier otro error propio de la tarea.

  Los errores de oleada que no pertenecen a ninguna tarea, como un cambio que nadie declara, rechazan la oleada pero no cambian el resultado de las tareas.
- `mth plan stats` resume esos eventos por modelo: intentos, `ok`, fallidos y porcentaje de `ok`. Opcionalmente se limita a una spec (`--spec SPEC-NNNN`). Un mismo intento verificado varias veces (misma spec, tarea, modelo y huella de manifiesto) cuenta una vez, con su último resultado. Las líneas ilegibles de la traza se saltan y se cuentan en un aviso.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | `[models]` inválida: escalera vacía o con repetidos, alias desconocido, rol fuera de la escalera, tipo erróneo | Fail-fast: ningún comando se ejecuta; el error nombra la clave | AC-02 |
| FM-02 | Celda `Modelo` con un alias fuera de la escalera | `mth plan check` / `mth trace`: error del plan con su línea | AC-03 |
| FM-03 | `plan model` de una tarea inexistente, o spec sin plan | Error; no se imprime ningún alias | AC-04 |
| FM-04 | `--model` mal formado, con alias desconocido o de una tarea ajena a la oleada | `mth plan verify`: error; no se verifica ni registra nada | AC-06 |
| FM-05 | Traza ausente | `mth plan stats` informa de que no hay datos (no es error) | AC-08 |
| FM-06 | Líneas de la traza corruptas o ajenas | Se saltan, se cuentan en un aviso y el resumen sigue con las legibles | AC-08 |
| FM-07 | Escritura de la traza imposible | `Tracer`: aviso único y la operación sigue (fail-open documentado en `log.py`); las métricas son informativas | AC-05 |

## Criterios de aceptación

- **AC-01**: MIENTRAS no exista la tabla `[models]`, la configuración DEBE usar `ladder = ["haiku", "sonnet", "opus"]` y `sonnet` para `task`, `review` y `documenter`, y `mth models` DEBE mostrarlo.
- **AC-02**: SI `[models]` tiene una escalera vacía o con alias repetidos, un alias fuera de `haiku`, `sonnet`, `opus` y `fable`, o un `task`, `review` o `documenter` fuera de la escalera, ENTONCES la carga de la configuración DEBE rechazarla.
- **AC-03**: CUANDO se ejecuta `mth plan check`, `mth` DEBE aceptar la cabecera de cuatro columnas y la de cinco con `Modelo`, tomar `models.task` en una celda vacía y mostrar el nivel efectivo de cada tarea; SI un alias no está en la escalera, ENTONCES DEBE rechazarlo con su línea.
- **AC-04**: CUANDO se ejecuta `mth plan model`, `mth` DEBE imprimir solo el nivel efectivo de la tarea (con `--retry`, el siguiente de la escalera o el último si ya lo es); SI la tarea no existe, ENTONCES DEBE fallar sin imprimir alias.
- **AC-05**: CUANDO se ejecuta `mth plan verify`, `mth` DEBE registrar un evento `plan.task` por tarea de la oleada con el modelo (el de `--model` o el efectivo), el resultado (`ok`, `not_run`, `not_completed` o `rejected`) y la huella del manifiesto, también si rechaza la oleada.
- **AC-06**: SI `--model` está mal formado, trae un alias fuera de la escalera o es de una tarea ajena a la oleada, ENTONCES `mth plan verify` DEBE rechazarlo sin verificar ni registrar nada.
- **AC-07**: CUANDO se ejecuta `mth plan stats`, `mth` DEBE resumir por modelo intentos, `ok`, fallidos y porcentaje de `ok`, contar una sola vez un intento repetido con la misma huella y filtrar por spec con `--spec`.
- **AC-08**: SI la traza no existe, ENTONCES `mth plan stats` DEBE informar de que no hay datos; SI hay líneas ilegibles, ENTONCES DEBE saltarlas y contarlas en un aviso.

## Notas

Sin plan de trabajo: la implementa la sesión principal.
