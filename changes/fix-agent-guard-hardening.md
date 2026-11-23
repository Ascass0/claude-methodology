---
bump: patch
refs: SPEC-0012
---
### Corregido
- Un agente del catálogo que pierde la cabecera de su `.md` ya no queda sin restricciones: si tiene guard, se bloquea hasta `mth agents sync --force` o `mth agents remove`, y `mth doctor` lo avisa.
- El guard de los agentes de solo lectura ya no se puede sortear con un programa con ruta (`./git`), expansiones de shell (`$'…'`, llaves, comodines) ni filtros que escriben (`sort -o`, `uniq entrada salida`). `respondedor-incidencias` ya no admite `git fetch` ni `git branch -r -d`.
- Los trabajadores no pueden escribir en los ficheros que definen sus propias restricciones (`.claude/hooks/`, `.claude/mth/`, `.claude/agents/`, `.claude/settings*.json`, `.git`).
- El guard tiene límites de tiempo: si `git` no responde, bloquea en lugar de dejar que el hook venza y la llamada pase.
- Sin lanzador (plugin ausente o anterior a 0.8.0), solo se bloquea a los agentes del catálogo; `verificador`, `documentador` y los demás siguen funcionando.
- `mth agents add` escribe el shim y la entrada del hook antes que los agentes, con escrituras atómicas, y al quitar el hook conserva los hooks propios que compartan entrada.
- `mth db-query` solo abre bases dentro del repositorio, exige límites positivos y acota la longitud de los valores y de las celdas.
- Cada decisión del guard sobre un agente del catálogo queda registrada en `.git/mth/agent-guard.jsonl`, con traceback si es un error interno.
