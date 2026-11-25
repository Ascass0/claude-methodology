# SPEC-0017 · Decisión autónoma de versión

- Estado: implementada
- Fecha: 2026-11-24
- Formato: compacto
- ADRs: [ADR-0013](../adr/process/ADR-0013-decision-autonoma-de-version.md)
- Sustituye a: —


## Contexto

- `mth release` publicaba lo que hubiera en `changes/` con el mayor `bump` declarado, sin decir si merece la pena ni si el nivel es coherente.
- [ADR-0013](../adr/process/ADR-0013-decision-autonoma-de-version.md) lo convierte en una decisión determinista y autónoma.

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

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Fragmento con `bump` por debajo del mínimo | `mth integrate` y `mth release`: error que nombra el fragmento, el nivel y el mínimo; no se integra ni se publica | AC-01, AC-02 |
| FM-02 | Nivel `major` que cruzaría `1.0.0` | `mth release` y `--plan`: error o `bloqueado`; solo `--allow-major` lo permite | AC-05 |
| FM-03 | `--plan` fuera de `development` | Error con la pista de cambiar a `development` | AC-03 |
| FM-04 | Fragmento ilegible o con referencias inexistentes | El error de validación de siempre; no se decide nada | AC-03 |
| FM-05 | Ramas remotas ilegibles | `--plan` decide sin ellas y avisa; no emite `esperar` | AC-04 |

## Criterios de aceptación

- **AC-01**: El mínimo de un fragmento DEBE ser `minor` para `feat` y `patch` para el resto, y subir a `minor` (antes de `1.0.0`) o `major` (desde `1.0.0`) con la sección de eliminaciones, en español y en inglés; SI el `bump` está por debajo, ENTONCES DEBE dar un error que lo explique.
- **AC-02**: SI una rama de primer nivel tiene un fragmento por debajo de su mínimo, ENTONCES `mth integrate` DEBE rechazarla, y `mth release` DEBE rechazarlo antes de crear la rama de release.
- **AC-03**: CUANDO se ejecuta `mth release --plan`, `mth` DEBE imprimir los fragmentos con su nivel, el nivel resultante, la versión propuesta y la decisión con sus motivos, sin modificar nada (ramas, ficheros ni etiquetas).
- **AC-04**: La decisión DEBE ser `no publicar` sin fragmentos, `bloqueado` con un fragmento por debajo del mínimo, `esperar` con ramas de trabajo abiertas que aportan fragmento y `publicar` en los demás casos.
- **AC-05**: SI el nivel resultante es `major` con la última versión menor que `1.0.0`, ENTONCES la decisión DEBE ser `bloqueado` y `mth release` DEBE rechazarlo; CON `--allow-major`, DEBE publicar `1.0.0`.
- **AC-06**: `mth release` DEBE publicar la misma versión que `--plan` propone y dejar en la traza la decisión y sus motivos.
- **AC-07**: Las skills `mth-release` y `mth-develop` DEBEN documentar la decisión autónoma (`mth release --plan` tras integrar, las cuatro decisiones y su respuesta).

## Notas

Modifica el criterio de publicación de la skill `mth-release` («Cuándo: hay fragmentos, las features integradas funcionan en conjunto…»): ahora lo calcula `mth release --plan`.
