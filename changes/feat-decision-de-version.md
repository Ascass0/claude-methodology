---
bump: minor
refs: SPEC-0017, ADR-0013
---
### Añadido
- `mth release --plan` decide, sin escribir nada, si hay que publicar y con qué nivel: imprime los fragmentos con su nivel, el nivel resultante (SemVer), la versión propuesta y una decisión con sus motivos (`publicar`, `esperar`, `no publicar` o `bloqueado`), que queda en la traza.
- Cada fragmento tiene un nivel mínimo: `feat` → `minor`, el resto → `patch`, y eliminar funcionalidad (sección `Eliminado`) → `minor` en `0.y.z` y `major` desde `1.0.0`. `mth integrate` y `mth release` rechazan un `bump` por debajo del mínimo.
- `mth release --allow-major`: `1.0.0` declara la API estable y solo se publica con esa decisión explícita; sin ella, un nivel `major` antes de `1.0.0` queda bloqueado.

### Cambiado
- Las skills `mth-release` y `mth-develop` indican que, tras integrar en `development`, el agente decide solo si publicar con `mth release --plan` y publica cuando recomienda `publicar`.
