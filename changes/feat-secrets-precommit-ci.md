---
bump: minor
refs: SPEC-0024, ADR-0022
---
### Añadido
- `mth secrets --staged` escanea con `gitleaks` solo lo preparado para el commit. Falla cerrado: sin `gitleaks`, con un error de la herramienta o al agotar el tiempo, no da nada por limpio. Requiere `gitleaks` 8.19.0 o posterior.
- Hook `pre-commit` opcional (`secrets.hook = "on"`) que rechaza el commit si hay secretos preparados. `hooks.pre_commit` (`own`, `replace`, `chain`) decide cómo convive con un hook ajeno. `git commit --no-verify` lo salta.
- Workflow de CI opcional `.github/workflows/secrets.yml` (`secrets.ci = "on"`, solo con GitHub y CI exigida) que escanea cada PR y cada push a `main` y `development` con un binario de `gitleaks` fijado. `mth` lo escribe con una marca en la primera línea y no sobrescribe un fichero ajeno. La protección de rama debe exigir su comprobación, porque una rama puede editarlo.
- La adopción incluye la pregunta `secretos` (`bloquear`, `integrar`, `ninguno`); un repo nuevo hace como mucho seis preguntas, en dos rondas. `mth update` lista las brechas `secretos-hook` y `secretos-ci` (decisión) y `secretos-workflow` (automática), y `mth doctor` informa del estado y de la versión de `gitleaks`.
- Las claves nuevas `secrets.hook` y `secrets.ci` nacen sin decidir (`""`) y `hooks.pre_commit` es `own`. Un plugin anterior las rechaza al cargar la configuración: actualiza el plugin antes de aceptar las brechas. Ni el hook ni el workflow se activan solos.
