---
bump: minor
refs: SPEC-0023
---
### Añadido
- Toda idea `feat`, `fix` o `hotfix` necesita un plan acordado con la persona antes de crear la rama. El plan es un fichero local `.work/plans/PLAN-NNNN-slug.md` que no se commitea.
- `mth plan new`, `agree`, `list`, `show` y `done` gestionan los planes acordados. `mth branch --plan PLAN-NNNN` crea la rama contra un plan acordado y `mth integrate` y `mth hotfix finish` exigen que la rama figure en un plan en curso.
- Sección `[plans]` (`required_for`, por defecto `feat`, `fix` y `hotfix`) y clave `[roles].planner` en `.claude/methodology.toml`.
- Agente del plugin `planificador` (siempre Opus, solo lectura): redacta el plan y recomienda los agentes del catálogo que conviene instalar.
- Skill `mth-plan` para redactar, discutir y acordar el plan; el ciclo de `mth-develop` y las reglas base incluyen el paso «plan acordado».
- El `orquestador` (1.1.0) instala los agentes del catálogo que el plan recomienda y reparte el trabajo según el plan. El `verificador` avisa si el diff se sale del plan.
