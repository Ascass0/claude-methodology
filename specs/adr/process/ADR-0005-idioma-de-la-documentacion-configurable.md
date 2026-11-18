# ADR-0005 · Idioma de la documentación configurable

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

PRINCIPLES §5 y §7 fijan el idioma: el código y los commits, en inglés; la documentación, las specs, el changelog y los PR, en español. `mth` reconoce palabras clave en español en las specs (estado, plan de trabajo) y en los fragmentos de changelog. Un repo con documentación en inglés que adopta la metodología tendría que traducirla o mezclar idiomas en el mismo documento. La adopción guiada ([SPEC-0004](../../features/SPEC-0004-adopcion-guiada.md)) detecta el idioma y tiene que poder respetarlo.

## Decisión

1. Una clave `language.docs` admite `es` (por defecto) e `en`. El código y los commits siguen en inglés en todos los casos.
2. Cada idioma tiene sus propias palabras clave y plantillas, y `mth` reconoce **solo** las del idioma configurado. Así, un documento no puede mezclar idiomas sin que `mth` lo detecte.
3. Las palabras clave de cada idioma viven en un único módulo de `mth`, del que leen la trazabilidad, el plan y el changelog.
4. Los mensajes de `mth`, las skills y `PRINCIPLES.md` siguen en español. Son la interfaz de la metodología, no documentación del repo.
5. PRINCIPLES §5 y §7 pasan a decir que la documentación se escribe en el idioma de `language.docs`.

## Alternativas consideradas

- **Reconocer los dos idiomas a la vez:** más tolerante, pero permite specs con el estado en un idioma y el plan en otro, y el plan de trabajo tendría dos cabeceras válidas.
- **Cualquier idioma, con palabras clave configurables:** el modelo de datos sería mucho más complejo (tablas de traducción en la configuración) para una necesidad que hoy solo existe en inglés.
- **Traducir también mensajes y skills:** duplica todo el texto de la metodología, y su mantenimiento, sin cambiar lo que se produce en el repo.

## Consecuencias

- **Positivas:** un repo en inglés adopta la metodología sin traducir nada y sin mezclar idiomas.
- **Negativas:** las plantillas existen por duplicado, y un test comprueba que las dos versiones tienen la misma estructura.
- **Riesgo aceptado:** quien trabaje en un repo en inglés leerá los mensajes de `mth` en español.
