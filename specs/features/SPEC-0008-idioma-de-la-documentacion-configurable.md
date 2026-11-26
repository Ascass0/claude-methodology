# SPEC-0008 · Idioma de la documentación configurable

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: ADR-0005
- Sustituye a: —


## Contexto

- Código y commits en inglés; documentación, specs, changelog y PR en español.
- Las plantillas están en español y `mth` reconoce palabras clave en español: el estado de una spec (`- Estado: implementada`), `## Plan de trabajo` y sus columnas, las secciones del changelog (`Añadido`, `Corregido`…).
- Un repo con documentación en inglés no puede adoptar la metodología sin mezclar idiomas.
- Decisión: [ADR-0005](../adr/process/ADR-0005-idioma-de-la-documentacion-configurable.md).

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

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Idioma desconocido | Fail-fast al cargar la configuración | AC-02 |
| FM-02 | Fragmento con una sección de otro idioma | `mth changes check` y gates: error con las secciones válidas del idioma | AC-04 |
| FM-03 | Spec con el estado en otro idioma | `mth trace`: no se reconoce como implementada, igual que con un estado mal escrito | AC-05 |

## Criterios de aceptación

- **AC-01**: MIENTRAS no exista la tabla `[language]`, `mth` DEBE funcionar en español como hasta ahora.
- **AC-02**: SI `language.docs` no es `es` ni `en`, ENTONCES la carga de la configuración DEBE rechazarlo.
- **AC-03**: MIENTRAS `language.docs = "en"`, `mth doc spec` y `mth doc adr` DEBEN crear documentos con las plantillas en inglés.
- **AC-04**: MIENTRAS `language.docs = "en"`, `mth` DEBE validar los fragmentos con las secciones en inglés, rechazar una sección en español y escribirlas en inglés al publicar.
- **AC-05**: MIENTRAS `language.docs = "en"`, `mth trace` DEBE exigir tests para los criterios de una spec con `- Status: implemented`.
- **AC-06**: MIENTRAS `language.docs = "en"`, `mth plan check` DEBE reconocer `## Work plan` con sus columnas en inglés.
- **AC-07**: Las reglas de sesión DEBEN indicar el idioma configurado de la documentación.
- **AC-08**: MIENTRAS `language.docs = "en"`, `mth init` DEBE escribir el CHANGELOG y el bloque de CLAUDE.md en inglés y `mth branch` DEBE crear el fragmento en inglés.

## Notas

—
