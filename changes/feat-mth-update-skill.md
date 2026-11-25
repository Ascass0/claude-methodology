---
bump: minor
refs: SPEC-0021, ADR-0017
---
### Añadido
- `mth update --plan` lista las brechas entre un repo adoptado y lo que exige el plugin instalado (configuración, agentes del catálogo, bloque de CLAUDE.md, hook, formato de specs y ADR).
- `mth update` aplica en `chore/update-methodology` las brechas deterministas sin cambiar ninguna decisión ya tomada y deja un ADR de actualización.
- Skill `mth-update`: la persona la invoca cuando el plugin se ha actualizado; conduce las decisiones y migraciones y se integra por PR.
