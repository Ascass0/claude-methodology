# SPEC-0008 · Idioma de la documentación configurable

- Estado: aprobada
- Fecha: 2026-11-18
- ADRs: ADR-0005
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0008/AC-NN`. -->

## Contexto

La metodología escribe el código y los commits en inglés, y la documentación, las specs, el changelog y los PR en español. Las plantillas están en español y `mth` reconoce palabras clave en español: el estado de una spec (`- Estado: implementada`), la sección `## Plan de trabajo` y sus columnas, y las secciones del changelog (`Añadido`, `Corregido`…). Un repo con documentación en inglés no puede adoptar la metodología sin mezclar dos idiomas. [ADR-0005](../adr/process/ADR-0005-idioma-de-la-documentacion-configurable.md) recoge la decisión.

## Objetivo

El repo elige el idioma de su documentación entre español e inglés. Las plantillas, las palabras clave que reconoce `mth` y las reglas de sesión siguen ese idioma.

## Fuera de alcance

- Otros idiomas.
- Los mensajes de `mth`, los textos de las skills y `PRINCIPLES.md`, que siguen en español.
- El idioma del código y de los commits, que sigue siendo el inglés.

## Comportamiento

Tabla nueva `[language]`, con la clave `docs`: `es` (por defecto) o `en`. Cada idioma reconoce solo sus propias palabras clave:

| Elemento | `es` | `en` |
|---|---|---|
| Estado de spec | `- Estado:` borrador, aprobada, implementada, sustituida | `- Status:` draft, approved, implemented, superseded |
| Plan de trabajo | `## Plan de trabajo` · Tarea, Oleada, Ficheros, Criterios, Modelo | `## Work plan` · Task, Wave, Files, Criteria, Model |
| Secciones del changelog | Añadido, Cambiado, Obsoleto, Eliminado, Corregido, Seguridad | Added, Changed, Deprecated, Removed, Fixed, Security |
| Plantillas | `templates/` | `templates/en/`: spec, ADR, CHANGELOG, bloque de CLAUDE.md y fragmento |

- `mth doc spec`, `mth doc adr`, `mth init` y el fragmento que crea `mth branch` usan las plantillas del idioma.
- Las reglas de sesión indican el idioma de la documentación.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Idioma desconocido | Carga de la configuración | Fail-fast |
| Fragmento con una sección de otro idioma | `mth changes check`, gates | Error con las secciones válidas del idioma |
| Spec con el estado en otro idioma | `mth trace` | No se reconoce como implementada, igual que hoy con un estado mal escrito |

## Criterios de aceptación

- **AC-01**: Sin la tabla `[language]`, todo funciona como hasta ahora, en español.
- **AC-02**: La carga de la configuración rechaza un idioma distinto de `es` o `en`.
- **AC-03**: Con `en`, `mth doc spec` y `mth doc adr` crean documentos con las plantillas en inglés.
- **AC-04**: Con `en`, los fragmentos se validan con las secciones en inglés, se rechaza una sección en español y la publicación las escribe en inglés.
- **AC-05**: Con `en`, `mth trace` exige tests para los criterios de una spec con `- Status: implemented`.
- **AC-06**: Con `en`, `mth plan check` reconoce `## Work plan` con sus columnas en inglés.
- **AC-07**: Las reglas de sesión indican el idioma configurado de la documentación.
- **AC-08**: Con `en`, `mth init` escribe el CHANGELOG y el bloque de CLAUDE.md en inglés, y `mth branch` crea el fragmento en inglés.

## Notas

—
