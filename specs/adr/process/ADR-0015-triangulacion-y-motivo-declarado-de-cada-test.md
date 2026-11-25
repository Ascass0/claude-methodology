# ADR-0015 · Triangulación y motivo declarado de cada test

- Estado: aceptado
- Fecha: 2026-11-25
- Categoría: process
- Formato: compacto

## Contexto

- PRINCIPLES §6 cuenta los tests necesarios; `revisor-parsimonia` marca los que sobran. Tres carencias:
  - Un solo ejemplo por AC permite una solución fija: un agente que busca el verde escribe casos especiales para los valores del test. La triangulación de TDD lo evita: dos ejemplos de clases distintas obligan a generalizar.
  - Eliminar el andamiaje tras el refactor depende del criterio y nada lo comprueba.
  - Solo los tests de AC declaran por qué existen (`verifies:`); el resto es indistinguible del andamiaje.
- Lo comprobable se automatiza (§0). El orden rojo → verde → refactor no es verificable; el estado final sí.
- Los repos adoptados tienen tests anteriores sin etiquetar.
- Depende de [ADR-0014](ADR-0014-formato-compacto-de-specs-y-adr.md) (IDs `FM-NN`).

## Decisión

1. **Triangulación (§6).** Todo AC cuya salida dependa de la entrada DEBE tener al menos dos ejemplos de clases de equivalencia distintas: dos tests, o uno parametrizado con dos casos o más. Un AC sin entrada variable (`SI falta X, ENTONCES falla`) queda exento. [criterio]
2. **Cada test declara por qué existe** con una etiqueta: `verifies: SPEC-NNNN/AC-NN`, `verifies: SPEC-NNNN/FM-NN`, `regression: <issue o referencia>` o `unit: <símbolo público>`. Un test sin etiqueta es andamiaje: `mth trace` lo reporta como error y bloquea `mth integrate`. En ficheros legados (SPEC-0005) es solo aviso. [script]
3. **Detección:** patrones por lenguaje en `trace.test_patterns` (glob → regex de la línea que abre un test), con valores por defecto para Python, JS/TS y Go. Sin patrón para su lenguaje, un fichero de tests con nombre de test y extensión de código DEBE llevar al menos una etiqueta. [script]
4. **Eliminar andamiaje.** Dos tests de la misma clase de equivalencia para el mismo AC: sobra uno y `revisor-parsimonia` indica cuál. Un test se conserva solo si aporta una clase, un límite o un modo de fallo propio. [criterio]
5. Una implementación con casos especiales para los valores del test es bloqueante en `revisor-fallos`. [criterio]
6. `mth trace` avisa (sin error) de los AC con un único test para que el revisor valore si hace falta triangular. [script]
7. `mth-develop` describe el ciclo: primer ejemplo en rojo → verde mínimo → segundo ejemplo de otra clase → generalizar → refactor → eliminar andamiaje. Se impone el estado final, no el orden.
8. Cambio incompatible: se marca con `!` y `BREAKING CHANGE:`, y el CHANGELOG explica cómo migrar. Antes de 1.0.0 es nivel `minor`.

## Rechazado

- TDD estricto borrando el código escrito antes que el test: el orden no es verificable y borrar código es destructivo.
- Solo criterio del revisor, sin etiquetas: es lo de hoy; eliminar el andamiaje depende de que alguien se acuerde.
- Mutation testing como gate: detecta tests que faltan, no que sobran, y es caro. Si se quiere, será otro ADR opcional por repo.
- Dos tests en todo AC: obliga a duplicar tests donde no hay entrada variable.
- Etiqueta en una línea fija (justo tras la definición): rompe con decoradores, docstrings y estilos de cada lenguaje; la región del test es más tolerante.

## Consecuencias

- **+** Las soluciones fijas se vuelven detectables, cada test tiene un motivo trazable y el andamiaje sin etiqueta lo marca un script.
- **−** Hay que etiquetar los tests nuevos. Los patrones por lenguaje son una heurística que mantener.
- **riesgo** Un patrón que reconoce como test una línea que no lo es (una cadena) da un falso error → se ajusta `trace.test_patterns` o `trace.exclude`.
- **riesgo** Etiquetar por inercia (`unit:` en todo) vacía la regla → `revisor-parsimonia` revisa que la etiqueta diga la verdad.
- **riesgo** Repos adoptados: un test nuevo sin etiqueta bloquea la integración → se migra con `trace.legacy_base` o etiquetando.

## Impone

- [script] `mthlib/trace.py` (etiquetas, aviso de un único test), `mthlib/config.py` (`trace.test_patterns`).
- [criterio] `revisor-parsimonia` (andamiaje, etiquetas veraces) y `revisor-fallos` (casos especiales).
- [criterio] `mth-develop` (ciclo) y PRINCIPLES §6.
