# ADR-0014 · Formato compacto de specs y ADR

- Estado: aceptado
- Fecha: 2026-11-24
- Categoría: process
- Formato: compacto

## Contexto

- Los documentos están escritos en prosa para personas; su lector principal es un agente y cada palabra cuesta contexto.
- El coste pesa sobre todo en lo que se carga en **todas** las sesiones: `context/core.md`, bloque de `CLAUDE.md`, descripciones de skills y agentes, `PRINCIPLES.md` (que `core.md` manda leer). Specs y ADR solo se leen cuando hacen falta.
- Comprimir de más pierde negaciones y condiciones: se mantiene DEBE / NO DEBE (RFC 2119).
- Las personas siguen aprobando specs y revisando PR: compacto, pero legible.
- En un ADR el porqué y lo rechazado evitan que se vuelva a proponer lo descartado: se recorta prosa, no razonamiento.
- El ADR de los tests necesita IDs de modo de fallo.
- Estándares existentes: EARS (plantillas de requisitos), Y-statements (decisión en campos fijos, compatible con MADR).

## Decisión

1. Criterios de aceptación en **EARS**, con las palabras clave del idioma de `language.docs` (`lang.py`):
   - `AC-NN: CUANDO <disparador>, <sistema> DEBE <respuesta>.`
   - `AC-NN: SI <condición>, ENTONCES <sistema> DEBE <respuesta>.`
   - `AC-NN: MIENTRAS <estado>, <sistema> DEBE <respuesta>.`
   - `AC-NN: <sistema> DEBE <respuesta>.` (requisito permanente)
   - En inglés: `WHEN`, `IF … THEN`, `WHILE`, `SHALL` / `MUST`.
2. Modos de fallo con ID en tabla: `| FM-NN | Causa | Respuesta | Cubierto por |`. Los IDs son únicos en la spec y se referencian como `SPEC-NNNN/FM-NN`.
3. ADR con campos fijos (estilo Y-statement): `Contexto` (pocas líneas), `Decisión` (numerada, con DEBE / NO DEBE), `Rechazado` (`alternativa: motivo`), `Consecuencias` (`+` / `−` / `riesgo`), `Impone` (`[script]`, `[hook]` o `[criterio]`, con su ubicación).
4. PRINCIPLES §7 fija el estilo de specs, ADR y documentos inyectados: una regla por línea; tablas y campos en lugar de párrafos; referencias por ID en lugar de repetir; sin introducciones ni resúmenes finales.
5. `mth trace` comprueba: campos obligatorios del ADR, patrón EARS de cada `AC-NN`, unicidad de los `FM-NN` y que toda referencia `FM-NN` o `SPEC-NNNN/FM-NN` apunta a uno existente. NO DEBE comprobar la longitud: es criterio de `revisor-adr`.
6. Un documento declara el formato con la línea de cabecera `- Formato: compacto` (`- Format: compact`). `mth trace` aplica las comprobaciones del punto 5 solo a los documentos que la llevan. Los existentes no se convierten y siguen como están; se adaptan cuando alguien los toca.
7. Lo que se carga siempre (`core.md`, `PRINCIPLES.md`, descripciones de skills y agentes) se reescribe en este estilo en la misma versión. NO DEBE perderse ninguna regla, solo prosa; DEBE medirse su tamaño antes y después, y las dos cifras van en el PR.
8. Plantillas `templates/spec.md` y `templates/adr.md` (ES y EN) actualizadas con la línea de formato y los campos.

## Rechazado

- Dos capas (resumen para el agente, prosa para personas): duplica la fuente de verdad (§7) y se desincronizan.
- Estilo telegrama sin estructura: ahorra más, pierde condiciones y negaciones y no se valida.
- Pasar los documentos a inglés por coste: choca con `language.docs` (ADR-0005); si se plantea, primero se mide.
- Comprimir solo specs y ADR: deja fuera lo que más cuesta, lo que se carga en cada sesión.
- Validar todo documento por defecto (sin marca): rompería cada spec y ADR existente en el primer `mth trace`, contra «no se convierten». La marca hace explícito qué formato rige; sustituye al modo legado de SPEC-0005 solo en este eje.

## Consecuencias

- **+** Menos contexto por sesión (cifras en el PR). Criterios inequívocos y comprobables. Base de IDs `FM-NN` para el ADR de los tests.
- **−** Las personas pierden parte de la explicación. Las palabras clave EARS se mantienen en dos idiomas. Conviven dos formatos hasta que se toquen los existentes.
- **riesgo** Un patrón EARS demasiado rígido rechaza criterios válidos → la spec lo define con ejemplos reales del repo.
- **riesgo** Quien olvida la marca no tiene validación → las plantillas la incluyen.

## Impone

- [script] `mthlib/trace.py`: campos del ADR, EARS y `FM-NN`; `mthlib/lang.py`: palabras clave por idioma.
- [criterio] `revisor-adr`: longitud y estilo (PRINCIPLES §7).
- [criterio] Rescritura de lo que se carga siempre: sin pérdida de reglas.
- [criterio] Extensión (SPEC-0026): cabecera opcional `Seguridad` y etiqueta `[SEG]` en AC, validadas por `mthlib/compact.py`. Se amplía este ADR y no se crea otro porque no cambia la decisión (documentos validables por marca, EARS, sin romper los existentes) y solo añade un campo opcional del mismo formato.
