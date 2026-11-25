# SPEC-0005 · Modo legado en la trazabilidad

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: ADR-0003
- Sustituye a: —


## Contexto

- Un repo que adopta con contenido previo (specs sin criterios con test, enlaces fuera del repo, IDs con otro formato) tenía dos salidas: corregirlo todo antes de integrar (bloquea la adopción) o excluirlo con `trace.exclude` (deja de comprobarse para siempre, también al modificarlo).
- La adopción gradual ([SPEC-0004](SPEC-0004-adopcion-guiada.md), [ADR-0003](../adr/process/ADR-0003-adopcion-guiada-por-perfiles-de-destino.md)) necesita un punto intermedio: lo anterior queda visible como deuda sin bloquear y lo que se toca después cumple las reglas completas.

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

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | `trace.legacy_base` no es un hash completo | Fail-fast al cargar la configuración: ningún comando se ejecuta | AC-02 |
| FM-02 | El commit no existe en el repo (clon superficial, historia ajena) | `mth trace` y los gates: error que nombra el commit; los hallazgos no se rebajan a avisos (denegar, no degradar) | AC-06 |

## Criterios de aceptación

- **AC-01**: MIENTRAS no se declare `trace.legacy_base`, `mth trace` DEBE tratar todo hallazgo como un error.
- **AC-02**: SI `trace.legacy_base` no es un hash de 40 caracteres hexadecimales, ENTONCES la carga de la configuración DEBE rechazarlo.
- **AC-03**: SI un hallazgo está en un fichero sin cambios desde `trace.legacy_base`, ENTONCES `mth trace` DEBE tratarlo como aviso, terminar con éxito y mostrar cuántos hay.
- **AC-04**: SI un hallazgo está en un fichero modificado o creado después de `trace.legacy_base`, ENTONCES `mth trace` DEBE tratarlo como error.
- **AC-05**: CUANDO se ejecuta `mth trace --legacy`, `mth` DEBE listar cada hallazgo legado con su fichero y su línea.
- **AC-06**: SI el commit de `trace.legacy_base` no existe, ENTONCES `mth trace` DEBE fallar con un error que lo nombre.

## Notas

—
