---
bump: minor
refs: SPEC-0016, ADR-0012
---
### Añadido
- Clave `forge` (`github`, `gitlab` o `none`), deducida de la URL del remoto en la adopción (pregunta `forja`, siempre deducida) y escrita por `mth init`. Con `github` nada cambia.
- Con `gitlab` o `none`, `mth integrate` y `mth release` hacen solo la parte local y terminan con la lista de pasos manuales, sin llamar a `gh` y sin fusionar: `integrate` deja el título y la descripción del MR en `.work/merge-request/`, y `release` prepara `release/vX.Y.Z` con el `CHANGELOG.md` y marca los pasos que git confirma al repetirse.
- El guard bloquea `glab mr merge` igual que `gh pr merge`.

### Cambiado
- Sin GitHub, la adopción deduce `ci: sin-ci` y `versiones: continuar` (con etiquetas con prefijo y sin herramienta de publicación) en lugar de desactivar `mth integrate` y `mth release`; el plan previo las muestra como activas solo en su parte local.
- `mth doctor` no pide `gh` ni `ci.required` cuando `forge` no es `github`.
- `mth hotfix finish` falla antes de tocar nada con `gitlab` o `none`: fusionar sin poder comprobar la CI sería degradar.

