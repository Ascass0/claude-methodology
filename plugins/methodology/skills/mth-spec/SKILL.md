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
- **Plan de trabajo** (solo si vas a delegar dos o más tareas en agentes `dev-*`; skill `mth-develop`):

  ```markdown
  ## Plan de trabajo

  | Tarea | Oleada | Ficheros | Criterios |
  |---|---|---|---|
  | T-01 | 1 | `src/parser.py`, `tests/test_parser.py` | AC-01, AC-02 |
  | T-02 | 1 | `src/render/**` | AC-03 |
  | T-03 | 2 | `src/cli.py`, `tests/test_cli.py` | AC-04 |
  ```

  - Encabezado de nivel 2 exactamente `## Plan de trabajo` y estas columnas, en este orden.
  - `T-NN` únicos; oleada entera ≥ 1 (las tareas de una oleada van en paralelo; lo que depende de otra tarea va en una oleada posterior).
  - Ficheros entre comillas invertidas: rutas relativas exactas; un glob solo para ficheros cuyo nombre no se conoce. Tests incluidos.
  - Cada AC de la spec en al menos una tarea; ninguna tarea con criterios que la spec no declara.
  - Dos tareas de la misma oleada nunca comparten ficheros. Entre globs, `mth` asume solapamiento salvo que sus prefijos literales sean distintos: usa rutas exactas.
  - Ninguna decisión de diseño para quien implementa: si una tarea obliga a elegir un esquema, una API o cómo tratar un caso límite, fíjalo antes en la spec.
  - Columna opcional `Modelo` al final de la cabecera (`| Tarea | Oleada | Ficheros | Criterios | Modelo |`), con un alias de `models.ladder`; vacía = `models.task`. Elige el nivel por dificultad: `haiku` para lo mecánico (renombrados, fragmentos, ajustes repetitivos con el patrón dado), `sonnet` para implementar con criterio dentro de una spec cerrada, `opus` solo si la tarea exige razonamiento que la spec no puede fijar del todo.
  - Máximo 50 tareas. Valídalo con `mth plan check SPEC-NNNN` (también lo comprueba `mth trace`).

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
