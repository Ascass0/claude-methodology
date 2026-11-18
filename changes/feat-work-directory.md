---
bump: minor
refs: SPEC-0010, ADR-0006
---
### Añadido
- Directorio de trabajo local `.work/` en cada repo adoptado, con `plans/`, `merge-request/`, `security-report/`, `reviews/`, `notes/` y `tmp/`: ahí deja Claude planes, manifiestos, cuerpos de PR, informes y notas, en lugar del scratchpad de la sesión. El hook de sesión y `mth init` lo crean y lo excluyen de git en `.git/info/exclude`, sin modificar ningún fichero versionado. `mth doctor` lo comprueba y el guard bloquea los `git add` forzados que lo incluirían.
- `work.dirs` en `.claude/methodology.toml` añade subdirectorios propios del repo a `.work/`.

### Cambiado
- `mth-review` guarda los informes de los revisores en `.work/reviews/`, `mth-develop` los manifiestos de los agentes en `.work/plans/` y `mth-integrate` propone `.work/merge-request/` para los resúmenes largos de PR.
