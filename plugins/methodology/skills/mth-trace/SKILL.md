---
name: mth-trace
description: Comprueba la trazabilidad (IDs de specs y ADR definidos y únicos, referencias válidas, enlaces relativos dentro del repo, criterios cubiertos por tests, formato compacto) y guía la corrección. Úsala tras crear o renombrar specs, ADR o docs, tras mth sync, antes de integrar y cuando un gate reporte trazabilidad rota.
---

# Trazabilidad

`mth` es el comando del contexto de sesión (`$MTH`). `mth trace` lista todos los hallazgos con `fichero:línea`.

| Hallazgo | Corrección |
|---|---|
| `X definido dos veces` | Dos documentos con el mismo ID (habitual tras un merge de ramas paralelas). Renumera el más reciente con el siguiente libre y actualiza sus referencias |
| `referencia a X, que no está definido` | Crea el documento (skill `mth-spec`) o corrige el ID |
| `enlace roto` / `ancla inexistente` | Corrige la ruta o el encabezado. Las anclas siguen el formato de GitHub |
| `enlace fuera del repositorio` | Lo que vive en otro repo se enlaza con URL absoluta |
| `SPEC/AC-NN no tiene ningún test` | Añade el test con el comentario `verifies: SPEC-NNNN/AC-NN`, o devuelve la spec a `aprobada` si no está terminada |
| `un test verifica SPEC/AC-NN, que no existe` | El AC se renombró o eliminó: corrige el test o la spec |
| `AC-NN no sigue ningún patrón EARS` | Reescribe el criterio en una línea: `CUANDO …, … DEBE …`, `SI …, ENTONCES … DEBE …`, `MIENTRAS …, … DEBE …` o `… DEBE …` (en `language.docs = en`: `WHEN`, `IF … THEN`, `WHILE`, `SHALL`/`MUST`) |
| `FM-NN definido dos veces` / `fila de modos de fallo sin ID` | Cada fila de la tabla de modos de fallo lleva un `FM-NN` único |
| `referencia a FM-NN, que la spec no define` | Corrige el ID o añade el modo de fallo a su spec |
| `falta el campo «X» del ADR` | Añade el campo: `Contexto`, `Decisión`, `Rechazado`, `Consecuencias`, `Impone` |

## Convenciones que comprueba

- Un ID se **define** en un encabezado markdown que empieza por él, dentro de los ficheros de `ids.<tipo>.defined_in`.
- En el código, las referencias a decisiones son comentarios breves: `# ADR-NNNN: shared volume, not bind mounts`.
- En los tests, la cobertura de AC: `# verifies: SPEC-NNNN/AC-02` (un test puede verificar varios).

Si el repo tiene un esquema de IDs propio, se declara en `[ids]`; contenido que no debe comprobarse se excluye en `trace.exclude`, justificándolo en el commit.

## Formato compacto

Los documentos con la línea `- Formato: compacto` (`- Format: compact`) se validan con EARS, `FM-NN` y los campos del ADR; los demás, no. Las referencias `SPEC-NNNN/FM-NN` se comprueban siempre. Detalle en [SPEC-0018](../../../../specs/features/SPEC-0018-formato-compacto-de-specs-y-adr.md).

## Contenido legado

Si el repo declara `trace.legacy_base` (adopción gradual), los hallazgos en ficheros sin cambios desde ese commit son avisos: no bloquean ni los gates. `mth trace` muestra cuántos hay y `mth trace --legacy` los lista con `fichero:línea`. Un fichero que tocas o creas deja de ser legado: corrige sus hallazgos como cualquier otro. Detalle en [SPEC-0005](../../../../specs/features/SPEC-0005-modo-legado-en-la-trazabilidad.md).
