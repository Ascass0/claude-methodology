# SPEC-0005 · Modo legado en la trazabilidad

- Estado: implementada
- Fecha: 2026-11-18
- ADRs: ADR-0003
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0005/AC-NN`. -->

## Contexto

Un repo que adopta la metodología con contenido previo (specs sin criterios con test, enlaces que salen del repo, IDs con otro formato) tiene hoy dos salidas: corregirlo todo antes de integrar nada o excluirlo con `trace.exclude`. La primera bloquea la adopción. La segunda hace que ese contenido deje de comprobarse para siempre, también cuando alguien lo modifica.

La adopción gradual ([SPEC-0004](SPEC-0004-adopcion-guiada.md), [ADR-0003](../adr/process/ADR-0003-adopcion-guiada-por-perfiles-de-destino.md)) necesita un punto intermedio: lo anterior a la adopción queda visible como deuda sin bloquear, y lo que se toca después pasa a cumplir las reglas completas.

## Objetivo

1. Los hallazgos de trazabilidad en ficheros que no han cambiado desde la adopción son avisos, no errores.
2. Un fichero modificado o creado después de la adopción se comprueba con todas las reglas.
3. La deuda legada se ve en cada `mth trace` y se puede listar.

## Fuera de alcance

- Relajar otros gates (tests, revisión, CI).
- Marcar como legado ficheros concretos a mano: para eso sigue existiendo `trace.exclude`.

## Comportamiento

### Configuración

Clave nueva `trace.legacy_base`, vacía por defecto (sin modo legado). Su valor es el hash completo (40 caracteres hexadecimales) del commit a partir del cual se aplican las reglas completas. `mth init --answers` lo fija con el commit de partida de la adopción.

### Qué es legado

Un fichero es legado si existe en el árbol de `trace.legacy_base` y su contenido en el árbol de trabajo es idéntico al de ese commit. Un fichero creado después, o con cualquier cambio desde entonces, no es legado.

### Resultado de `mth trace`

- Los hallazgos de un fichero legado no son errores: no cambian el código de salida ni bloquean los gates de `mth integrate`, `mth release` o `mth hotfix finish`.
- Tras los errores, `mth trace` muestra `⚠ N hallazgos en contenido legado (anterior a <hash corto>): mth trace --legacy los lista`. Con `N = 0` no muestra nada.
- `mth trace --legacy` lista además cada hallazgo legado con su fichero y línea.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| `trace.legacy_base` no es un hash completo | Carga de la configuración | Fail-fast: ningún comando se ejecuta |
| El commit no existe en el repo (clon superficial, historia ajena) | `mth trace` y los gates | Error que nombra el commit; los hallazgos no se rebajan a avisos (denegar, no degradar) |

## Criterios de aceptación

- **AC-01**: Sin `trace.legacy_base`, `mth trace` se comporta como hasta ahora: todo hallazgo es un error.
- **AC-02**: La carga de la configuración rechaza un `trace.legacy_base` que no sea un hash de 40 caracteres hexadecimales.
- **AC-03**: Un hallazgo en un fichero sin cambios desde `trace.legacy_base` es un aviso: `mth trace` termina con éxito y muestra cuántos hay.
- **AC-04**: Un hallazgo en un fichero modificado después de `trace.legacy_base`, o creado después, es un error.
- **AC-05**: `mth trace --legacy` lista cada hallazgo legado con su fichero y su línea.
- **AC-06**: Si el commit de `trace.legacy_base` no existe, `mth trace` falla con un error que lo nombra.

## Notas

—
