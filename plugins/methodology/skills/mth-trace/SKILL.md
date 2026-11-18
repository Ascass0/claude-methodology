---
name: mth-trace
description: Comprueba la trazabilidad del repo (IDs de specs/ADR definidos y únicos, referencias válidas en código y docs, enlaces markdown relativos dentro del repo, criterios de aceptación cubiertos por tests) y guía la corrección. Úsala después de crear o renombrar specs, ADRs o docs, tras mth sync, antes de integrar y siempre que un gate reporte trazabilidad rota.
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

## Convenciones que comprueba

- Un ID se **define** en un encabezado markdown que empieza por él, dentro de los ficheros de `ids.<tipo>.defined_in`.
- En el código, las referencias a decisiones son comentarios breves: `# ADR-NNNN: shared volume, not bind mounts`.
- En los tests, la cobertura de AC: `# verifies: SPEC-NNNN/AC-02` (un test puede verificar varios).

Si el repo tiene un esquema de IDs propio, se declara en `[ids]`; contenido que no debe comprobarse se excluye en `trace.exclude`, justificándolo en el commit.
