---
bump: minor
refs: SPEC-0001, ADR-0001
---
### Añadido
- Plan de trabajo en la spec (sección `## Plan de trabajo`): tareas por oleadas con sus ficheros permitidos y sus criterios. `mth plan check SPEC-NNNN` lo valida antes de delegar: formato, criterios existentes y asignados, y que dos tareas de la misma oleada no compartan ficheros. `mth trace` aplica las mismas comprobaciones a toda spec que tenga la sección.
- `mth plan verify SPEC-NNNN --wave N --manifest FICHERO …` verifica una oleada contra los manifiestos JSON de sus agentes: rechaza tareas sin manifiesto (no ejecutadas), bloqueadas o fallidas (no completadas), manifiestos inválidos, criterios sin cubrir, tests ausentes o en rojo, ficheros fuera del alcance de la tarea, cambios que nadie declara y ficheros declarados sin cambios reales. Los desvíos se muestran como avisos.
- `mth-develop` describe el protocolo de delegación por oleadas: encargo con los ficheros permitidos de la tarea, manifiesto JSON guardado sin editar, verificación al cerrar cada oleada y un único reintento por tarea fallida.

### Cambiado
- `mth review record` exige `--report INFORME` y toma el número de bloqueantes de la última línea del informe del revisor (`BLOQUEANTES: N`). Un informe ausente, vacío, de más de 256 KiB o sin esa línea no se registra y la revisión sigue pendiente. `--blocking` desaparece: actualiza los scripts o hábitos que lo usen.
