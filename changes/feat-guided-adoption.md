---
bump: minor
refs: SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0008, ADR-0003, ADR-0004, ADR-0005
---
### Añadido
- Adopción guiada: `mth survey` inventaria el repo sin modificarlo, la skill `mth-init` conduce una entrevista con Opus que solo pregunta lo necesario, y `mth init --answers <json>` convierte las respuestas en configuración y en el ADR de adopción. `mth init --decline` desactiva el plugin en ese repo (`.claude/settings.local.json`, no versionado).
- `trace.legacy_base` y `mth trace --legacy`: en una adopción gradual, los hallazgos en ficheros sin cambios desde el commit base son avisos; lo que se toca después cumple todas las reglas.
- `hooks.commit_msg` con los valores `own`, `replace` y `chain`: decide qué hacer con un hook `commit-msg` ajeno al instalar el de `mth`.
- `autonomy.level` con los valores `full`, `until-pr` y `supervised`: el guard pide confirmación para integrar y publicar, o también para ramas, commits y push.
- `language.docs` con los valores `es` y `en`: idioma de docs, specs, ADR, changelog y PR, con plantillas en inglés. Código y commits siguen en inglés.

### Cambiado
- En un repo sin `.claude/methodology.toml`, el plugin ya no inyecta las reglas base ni bloquea comandos: el hook de sesión solo da el aviso de adopción y el guard no actúa hasta que se adopta.
- `PRINCIPLES.md` §5 (idioma del código, independiente del de la documentación), §7 (idioma de `language.docs`) y §11 (autonomía según `autonomy.level`).
