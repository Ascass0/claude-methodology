# SPEC-0002 · Niveles de modelo por tarea, escalado en el reintento y métricas

- Estado: aprobada
- Fecha: 2026-11-18
- ADRs: ADR-0002
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0002/AC-NN`. -->

## Contexto

Con [SPEC-0001](SPEC-0001-delegacion-verificable.md), la sesión principal reparte el trabajo en un plan y verifica cada oleada de forma determinista. Todas las tareas se delegan con el mismo modelo que la sesión principal, aunque su dificultad sea muy distinta. Hoy (precios de la API por millón de tokens de entrada/salida) Opus cuesta 4/20 $, Sonnet 2/10 $ y Haiku 0,10/0,50 $. Una tarea mecánica hecha con Opus cuesta unas 40 veces lo que costaría con Haiku.

Que un modelo más barato falle es aceptable porque `mth plan verify` lo detecta. Lo que falta es:

- decidir el modelo de cada tarea cuando se planifica, que es cuando mejor se conoce su dificultad;
- no repetir un intento fallido con el mismo modelo;
- datos para saber qué nivel funciona en cada tipo de tarea, en vez de ajustarlo a ojo (PRINCIPLES §2, optimización con evidencia).

## Objetivo

1. Cada tarea del plan tiene un **nivel de modelo**, declarado en el plan o tomado de la configuración del repo.
2. El reintento de una tarea fallida usa el **nivel siguiente** de una escalera configurable.
3. Cada verificación de oleada deja constancia del modelo y del resultado de cada tarea, y `mth` resume esas métricas por nivel.

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

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| `[models]` inválida: escalera vacía o con repetidos, alias desconocido, rol fuera de la escalera, tipo erróneo | Carga de la configuración | Fail-fast: ningún comando se ejecuta; el error nombra la clave |
| Celda `Modelo` con un alias fuera de la escalera | `mth plan check` / `mth trace` | Error del plan con su línea |
| `plan model` de una tarea que no existe, o spec sin plan | `mth plan model` | Error; no se imprime ningún alias |
| `--model` mal formado, con alias desconocido o de una tarea ajena a la oleada | `mth plan verify` | Error; no se verifica ni se registra nada |
| Traza ausente | `mth plan stats` | Informa de que no hay datos (no es un error) |
| Líneas de la traza corruptas o ajenas | `mth plan stats` | Se saltan, se cuentan en un aviso y el resumen sigue con las legibles |
| Escritura de la traza imposible | `Tracer` | Aviso único y la operación sigue (fail-open documentado en `log.py`): las métricas son informativas |

## Criterios de aceptación

- **AC-01**: Sin tabla `[models]`, la configuración usa `ladder = ["haiku", "sonnet", "opus"]` y `sonnet` para `task`, `review` y `documenter`, y `mth models` lo muestra.
- **AC-02**: La carga de la configuración rechaza una escalera vacía o con alias repetidos, un alias fuera de `haiku`, `sonnet`, `opus` y `fable`, y un `task`, `review` o `documenter` que no está en la escalera.
- **AC-03**: `mth plan check` acepta la cabecera de cuatro columnas y la de cinco con `Modelo`, toma `models.task` para una celda vacía, muestra el nivel efectivo de cada tarea y rechaza, con su línea, un alias que no está en la escalera.
- **AC-04**: `mth plan model` imprime solo el nivel efectivo de la tarea; con `--retry`, el siguiente de la escalera, o el último si ya lo es; y falla sin imprimir alias para una tarea inexistente.
- **AC-05**: `mth plan verify` registra un evento `plan.task` por tarea de la oleada, con modelo (el de `--model` o el efectivo), resultado (`ok`, `not_run`, `not_completed` o `rejected`) y huella del manifiesto, también cuando rechaza la oleada.
- **AC-06**: `mth plan verify` rechaza, sin verificar ni registrar, un `--model` mal formado, con alias fuera de la escalera o de una tarea que no pertenece a la oleada.
- **AC-07**: `mth plan stats` resume por modelo los intentos, `ok`, fallidos y porcentaje de `ok`, cuenta una sola vez un intento repetido con la misma huella y filtra por spec con `--spec`.
- **AC-08**: `mth plan stats` informa de que no hay datos si la traza no existe, y salta y cuenta en un aviso las líneas ilegibles.

## Notas

Sin plan de trabajo: la implementa la sesión principal.
