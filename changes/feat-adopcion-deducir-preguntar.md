---
bump: minor
refs: SPEC-0015, ADR-0011
---
### Añadido
- La adopción resuelve en código cada pregunta como `deducida`, `por_defecto` o `decision`, y solo pregunta las decisiones, en una sola ronda y empezando por la precedencia entre el repo y la metodología. Se deducen la rama de integración, el hook `commit-msg` ajeno, el comando de tests de `Makefile` o `justfile`, el idioma, el modo legado y, sin GitHub, la CI y la publicación (`mth survey --json` da `outcome`, `answer`, `basis` y `options` de cada pregunta).
- `mth init --answers FICHERO --plan` muestra, sin escribir nada, lo deducido, lo que va por defecto, lo decidido y las capacidades activas y desactivadas con su motivo; la adopción imprime el mismo plan antes de escribir.
- El ADR de adopción registra el resultado de cada pregunta en una columna nueva.
- La respuesta `revisores` admite `paths` para limitar un revisor del repo a unas rutas (`[review.paths]`).

### Cambiado
- Una opción que no funciona con el repo (por ejemplo, `ci: crear` o `versiones: continuar` sin GitHub) ya no se ofrece, y `mth init --answers` la rechaza.
- Las preguntas se ordenan por dependencia: `instrucciones` y `autonomia` van primero (también en `mth reconfigure`).

### Eliminado
- La opción `commits: sustituir`: un hook `commit-msg` ajeno solo se encadena, porque sustituirlo quitaba controles.
