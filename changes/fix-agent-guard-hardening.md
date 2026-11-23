---
bump: patch
refs: SPEC-0012
---
### Corregido
- Un agente del catálogo que pierde la cabecera de su `.md` ya no queda sin restricciones: si tiene guard, se bloquea hasta `mth agents sync --force` o `mth agents remove`, y `mth doctor` lo avisa.
- El guard de los agentes de solo lectura ya no se puede sortear con un programa con ruta (`./git`), expansiones de shell (`$'…'`, llaves, comodines), abreviaturas y grupos de opciones prohibidas (`git grep --open=sh`, `git grep -nOsh`, `gh api -iXPOST`) ni filtros que escriben o leen el entorno (`sort -o`, `uniq entrada salida`, `jq -n env`). `respondedor-incidencias` ya no admite `git fetch` ni `git branch -r -d`.
- Los trabajadores no pueden escribir en los ficheros que definen sus propias restricciones (`.claude/hooks/`, `.claude/mth/`, `.claude/agents/`, `.claude/settings*.json`, `.git`).
- El guard tiene límites de tiempo, también en macOS sin `timeout` (con `perl`; sin ninguno de los dos, bloquea): si `git` o el guard no responden, bloquea en lugar de dejar que el hook venza y la llamada pase. La protección de ficheros ignora las mayúsculas, como los sistemas de ficheros de macOS y Windows.
- Sin lanzador (plugin ausente o anterior a 0.8.0), solo se bloquea a los agentes del catálogo; `verificador`, `documentador` y los demás siguen funcionando.
- `mth agents add` escribe el shim y la entrada del hook antes que los agentes, con escrituras atómicas, y al quitar el hook conserva los hooks propios que compartan entrada.
- `mth db-query` solo abre bases dentro del repositorio, exige límites positivos y acota la longitud de los valores y de las celdas.
- Cada decisión del guard sobre un agente del catálogo queda registrada en `.git/mth/agent-guard.jsonl` (privado, sin el comando completo y con las credenciales redactadas), con traceback si es un error interno; el shim registra los cortes que el guard no puede registrar.
- `mth agents` informa de un fallo al escribir un fichero (disco lleno, permisos) como un error reanudable y no como un bug, y conserva los permisos de los ficheros que reescribe.
