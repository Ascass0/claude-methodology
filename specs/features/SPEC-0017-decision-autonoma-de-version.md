# SPEC-0017 · Decisión autónoma de versión

- Estado: implementada
- Fecha: 2026-11-24
- ADRs: [ADR-0013](../adr/process/ADR-0013-decision-autonoma-de-version.md)
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0017/AC-NN`. -->

## Contexto

`mth release` publica lo que haya en `changes/` con el mayor `bump` declarado, sin decir si merece la pena publicar ni si el nivel es coherente. [ADR-0013](../adr/process/ADR-0013-decision-autonoma-de-version.md) lo convierte en una decisión determinista y autónoma.

## Objetivo

1. `mth release --plan` dice, sin escribir nada, si se publica, qué versión y por qué.
2. El nivel declarado en cada fragmento no puede estar por debajo del mínimo que le corresponde por tipo y contenido.
3. `1.0.0` solo se publica con una decisión explícita.
4. El agente decide solo, tras cada integración, si publicar, y con qué nivel.

## Fuera de alcance

- Configurar la política de publicación (cada cuántos cambios, o por calendario): la regla es única.
- Calcular el nivel desde los commits.
- Publicar automáticamente desde `mth integrate`: la decisión la ejecuta el agente con las skills, bajo `autonomy.level`.

## Comportamiento

### Nivel mínimo de un fragmento

El tipo sale del prefijo del nombre del fragmento (`feat-…`, `fix-…`, `hotfix-…`, `security-…`):

| Condición | Mínimo |
|---|---|
| tipo `feat` | `minor` |
| otro tipo | `patch` |
| sección de eliminaciones (`Eliminado` / `Removed`) con contenido, última versión menor que `1.0.0` | `minor` |
| sección de eliminaciones con contenido, última versión `1.0.0` o mayor | `major` |

Se aplica el mayor de los mínimos. Un `bump` por debajo es un error que nombra el fragmento, el nivel declarado, el mínimo y el motivo. `mth integrate` (rama de primer nivel) y `mth release` lo comprueban antes de tocar nada.

### `mth release --plan`

Solo lee. Se ejecuta desde `development` (si no, falla con una pista). Imprime:

1. Cada fragmento con su nivel declarado.
2. El nivel resultante (el mayor), la última versión y la versión propuesta.
3. La decisión y sus motivos:

| Decisión | Cuándo |
|---|---|
| `no publicar` | No hay fragmentos: el mantenimiento sin fragmento no versiona |
| `bloqueado` | Un fragmento por debajo de su mínimo, o el nivel resultante es `major` con la última versión menor que `1.0.0` y sin `--allow-major` |
| `esperar` | Hay ramas de trabajo abiertas en el remoto (`feat`, `fix`, `hotfix`) que aportan fragmento; se listan |
| `publicar` | En los demás casos |

`esperar` es una recomendación: `mth release` no la comprueba. `no publicar` y `bloqueado` sí detienen `mth release`. La decisión y sus motivos van a la traza (`release.plan`).

### `mth release`

Calcula la versión con la misma decisión que `--plan`. Rechaza, antes de crear la rama de release, un fragmento por debajo de su mínimo y un `major` que cruzaría `1.0.0` sin `--allow-major`. Con `--allow-major` publica ese `major`. La reanudación de una release abierta no cambia.

### Autonomía (skills)

Las skills `mth-release` y `mth-develop` indican que, tras integrar en `development`, el agente ejecuta `mth release --plan` y, con `publicar`, ejecuta `mth release` (con `autonomy.level` `until-pr` o `supervised`, el guard pide antes la confirmación de la persona). Con `esperar`, sigue con el trabajo abierto; con `no publicar`, no publica; con `bloqueado`, corrige el fragmento o avisa si es `1.0.0`.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Fragmento con `bump` por debajo del mínimo | `mth integrate`, `mth release` | Error que nombra el fragmento, el nivel y el mínimo; no se integra ni se publica |
| Nivel `major` que cruzaría `1.0.0` | `mth release`, `--plan` | Error o `bloqueado`; solo `--allow-major` lo permite |
| `--plan` fuera de `development` | `mth release --plan` | Error con la pista de cambiar a `development` |
| Fragmento ilegible o con referencias inexistentes | `--plan`, `mth release` | El error de validación de siempre; no se decide nada |
| Ramas remotas ilegibles | `--plan` | Se decide sin ellas y se avisa; la recomendación `esperar` no se emite |

## Criterios de aceptación

- **AC-01**: El mínimo de un fragmento es `minor` para `feat`, `patch` para el resto, y sube a `minor` (antes de `1.0.0`) o `major` (desde `1.0.0`) con la sección de eliminaciones, en español y en inglés; un `bump` por debajo da un error que lo explica.
- **AC-02**: `mth integrate` rechaza una rama de primer nivel con un fragmento por debajo de su mínimo, y `mth release` rechaza lo mismo antes de crear la rama de release.
- **AC-03**: `mth release --plan` imprime los fragmentos con su nivel, el nivel resultante, la versión propuesta y la decisión con sus motivos, y no modifica nada (ni ramas, ni ficheros, ni etiquetas).
- **AC-04**: La decisión es `no publicar` sin fragmentos, `bloqueado` con un fragmento por debajo del mínimo, `esperar` con ramas de trabajo abiertas que aportan fragmento y `publicar` en los demás casos.
- **AC-05**: Un nivel `major` con la última versión menor que `1.0.0` es `bloqueado` y `mth release` lo rechaza; con `--allow-major` publica `1.0.0`.
- **AC-06**: `mth release` publica la misma versión que `--plan` propone, y la decisión y sus motivos quedan en la traza.
- **AC-07**: Las skills `mth-release` y `mth-develop` documentan la decisión autónoma (`mth release --plan` tras integrar, las cuatro decisiones y su respuesta).

## Notas

Modifica el criterio de publicación de la skill `mth-release` («Cuándo: hay fragmentos, las features integradas funcionan en conjunto…»): ahora lo calcula `mth release --plan`.
