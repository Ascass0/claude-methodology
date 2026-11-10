---
name: mth-spec
description: Crea y mantiene specs (qué se construye y cómo se acepta) y ADRs (por qué se decide) con numeración, plantilla y estados correctos. Úsala antes de implementar cualquier feature sin spec, cuando haya que tomar una decisión estructural, cuando cambie el estado de una spec o un ADR, o cuando la implementación revele que una spec estaba mal.
---

# Specs y ADRs

`mth` es el comando del contexto de sesión (`$MTH`). Escribe en español.

## Crear

- Spec: `mth doc spec --title "Título"` → `specs/features/SPEC-NNNN-titulo.md`
- ADR: `mth doc adr --title "Título" --category <categoría>` → `specs/adr/<categoría>/ADR-NNNN-titulo.md`

La spec de una feature se escribe dentro de su rama `feat/` (primer commit de la rama): si el fragmento de changelog aún no tiene refs, `mth` le añade el ID automáticamente. Nunca numeres a mano. Si dos ramas crean el mismo número en paralelo, `mth trace` lo detecta tras `mth sync`: renumera el tuyo y actualiza sus referencias.

## Contenido de una spec

- **Criterios de aceptación** con formato `- **AC-01**: …`, cada uno verificable por un test automático. Si un criterio no se puede automatizar, reformúlalo.
- **Modos de fallo**: cada fila genera al menos un test.
- **Fuera de alcance** explícito: evita que la feature crezca.
- Enlaza los ADR que la justifican (`ADR-NNNN`).

## Estados

| Documento | Transición | Cuándo |
|---|---|---|
| Spec | borrador → aprobada | Coherente con principios y ADR vigentes; AC verificables |
| Spec | aprobada → implementada | Al cerrar la feature: todos los AC tienen test (`mth trace` lo exige) |
| Spec | → sustituida | Otra spec la reemplaza: indícalo en "Sustituye a" de la nueva |
| ADR | propuesto → aceptado | Antes de implementar la decisión |
| ADR | → sustituido por ADR-NNNN / obsoleto | Nunca se borra un ADR |

Si la implementación demuestra que la spec estaba mal, corrige primero la spec (explicando el motivo en el commit) y después el código. Nunca al revés.

## Commit

Las specs y ADR se commitean en su propio commit temático: `docs(spec): …` o `docs(adr): …` con `Refs:` al propio ID.
