---
bump: minor
refs: SPEC-0020, ADR-0016
---
### Añadido
- Sección `[limits]` en la configuración: `max_file_lines` (1000 por defecto), `exclude` y `[[limits.exceptions]]`, donde `max_lines` (techo mayor que el límite) y `reason` son obligatorios; una excepción incompleta falla al cargar la configuración.
- `mth trace` aplica un trinquete sobre la diferencia con la rama padre: es error que la rama cree un fichero por encima del límite, lo haga cruzarlo o lo haga crecer estando ya por encima; también superar el techo de una excepción y una excepción caducada. Un fichero largo heredado que la rama no hace crecer solo avisa (`mth trace --limits` los lista). Se excluyen los binarios (los que `git` marca como tales o con un byte NUL) y los renombrados que git detecta se comparan con su origen.
- `revisor-diseno` (1.1.0) valora si el `reason` de cada excepción se sostiene frente a la responsabilidad única, con evals nuevas.
