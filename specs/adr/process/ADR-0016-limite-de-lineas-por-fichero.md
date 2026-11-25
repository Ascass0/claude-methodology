# ADR-0016 · Límite de líneas por fichero

- Estado: aceptado
- Fecha: 2026-11-25
- Categoría: process
- Formato: compacto

## Contexto

- Un fichero grande cuesta más contexto cada vez que un agente lo lee, fragmenta las ediciones y suele indicar que se incumple la responsabilidad única (§2, SOLID S). Hoy no hay límite.
- Hay ficheros grandes legítimos (tablas, gramáticas, código generado).
- Una excepción sin techo es barra libre: el fichero crece sin fin.
- Los repos adoptados ya tienen ficheros de miles de líneas: bloquear por ellos impediría integrar, y partir uno de 3000 líneas para un fix de una línea es desproporcionado (§12).
- Lo comprobable se automatiza (§0).

## Decisión

1. Un fichero versionado NO DEBE superar `limits.max_file_lines` (1000 por defecto) salvo excepción declarada. [script: `mth trace`]
2. Configuración `[limits]`: `max_file_lines`, `exclude` (globs) y `[[limits.exceptions]]` con `path`, `max_lines` (techo propio) y `reason` (no vacío) obligatorios y `refs` opcional. Una excepción incompleta o con `max_lines` no superior al límite es un error al cargar la configuración (fail-fast).
3. Medida: líneas físicas, es decir saltos de línea más uno si la última línea no termina en salto. Se excluyen los ficheros que `git` marca como binarios y los que contienen un byte NUL.
4. Trinquete sobre la diferencia con la rama padre (la rama destino de la rama de trabajo):
   - Error: la rama hace que un fichero supere el límite, o hace crecer uno que ya lo superaba, sin excepción.
   - Error: un fichero con excepción supera su `max_lines`.
   - Error: excepción caducada, porque ningún fichero suyo supera ya el límite.
   - Aviso: fichero por encima del límite que la rama no hace crecer.
5. Sin rama padre (`development`, `main`, ramas ajenas al flujo) no hay con qué comparar: el fichero largo es solo aviso. Los errores de excepciones no dependen de la rama.
6. Si hace falta comparar y la rama padre no se puede leer, `mth trace` falla nombrando la causa y cómo arreglarla: no relaja el límite. Solo se compara cuando algún fichero lo supera.
7. Un renombrado que git detecta se compara con el fichero de origen.
8. `revisor-diseno` valora si el `reason` se sostiene frente a la responsabilidad única: «es más cómodo» no vale; «partirlo separa cosas que cambian juntas» sí. [criterio]

## Rechazado

- Límite sin excepciones: rompe los casos legítimos y empuja a partir ficheros de forma artificial.
- Excepción en un comentario dentro del fichero: no tiene techo, se valida mal y queda repartida por el repo.
- Contar líneas lógicas o sin comentarios: depende del lenguaje y no es determinista entre lenguajes.
- Bloquear todo fichero por encima del límite aunque la rama no lo toque: bloquea la adopción con legado.
- Error ante un fichero largo sin rama padre: bloquearía `mth release` y los hotfix por legado ajeno a ellos.

## Consecuencias

- **+** El tamaño queda acotado y comprobado. Las excepciones son visibles, con techo y no se pudren. La adopción no se bloquea por el legado.
- **−** Una sección de configuración y una comprobación más. Un fichero cerca del límite obliga a partirlo o a justificarlo en una rama que no iba de eso.
- **riesgo** El límite aproxima la responsabilidad única: 900 líneas pueden incumplirla y 1200 no → el script acota el tamaño y el revisor valora la responsabilidad.
- **riesgo** Un renombrado que git no detecta cuenta como fichero nuevo → se declara una excepción.
- **riesgo** Checkout superficial sin la rama padre: falla solo si hay ficheros largos → se trae la rama (`git fetch`).

## Impone

- [script] `mthlib/limits.py` (medida y trinquete), `mthlib/flow.py` (integración en `mth trace`), `mthlib/config.py` (`[limits]`).
- [criterio] `revisor-diseno` (el `reason`) y PRINCIPLES §5.
