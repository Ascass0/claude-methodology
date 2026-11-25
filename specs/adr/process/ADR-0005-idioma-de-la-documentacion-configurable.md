# ADR-0005 · Idioma de la documentación configurable

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process
- Formato: compacto

## Contexto

- PRINCIPLES §5 y §7: código y commits en inglés; documentación, specs, changelog y PR en español.
- `mth` reconoce palabras clave en español en las specs (estado, plan de trabajo) y en los fragmentos de changelog.
- Un repo con documentación en inglés tendría que traducirla o mezclar idiomas en un mismo documento.
- La adopción guiada ([SPEC-0004](../../features/SPEC-0004-adopcion-guiada.md)) detecta el idioma y debe poder respetarlo.

## Decisión

1. `language.docs` DEBE admitir `es` (por defecto) y `en`. Código y commits NO DEBEN cambiar de idioma: siempre en inglés.
2. Cada idioma DEBE tener sus palabras clave y plantillas, y `mth` DEBE reconocer solo las del idioma configurado: un documento no puede mezclar idiomas sin que `mth` lo detecte.
3. Las palabras clave de cada idioma DEBEN vivir en un único módulo de `mth`, del que leen trazabilidad, plan y changelog.
4. Los mensajes de `mth`, las skills y `PRINCIPLES.md` DEBEN seguir en español: son la interfaz de la metodología, no documentación del repo.
5. PRINCIPLES §5 y §7 DEBEN decir que la documentación se escribe en el idioma de `language.docs`.

## Rechazado

- Reconocer los dos idiomas a la vez: permite el estado en un idioma y el plan en otro, y el plan tendría dos cabeceras válidas.
- Cualquier idioma con palabras clave configurables: tablas de traducción en la configuración para una necesidad que hoy solo existe en inglés.
- Traducir también mensajes y skills: duplica el texto de la metodología y su mantenimiento sin cambiar lo que se produce en el repo.

## Consecuencias

- **+** Un repo en inglés adopta la metodología sin traducir nada ni mezclar idiomas.
- **−** Las plantillas existen por duplicado; un test comprueba que ambas versiones tienen la misma estructura.
- **riesgo** Quien trabaje en un repo en inglés lee los mensajes de `mth` en español.

## Impone

- [script] `mthlib/lang.py`: vocabulario por idioma; `mthlib/config.py`: `language.docs`.
- [criterio] Test de estructura idéntica entre `templates/` y `templates/en/`.
