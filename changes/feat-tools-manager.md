---
bump: minor
refs: SPEC-0025, ADR-0023
---
### Añadido
- `mth tools` lista las herramientas externas que usa `mth` (hoy `gitleaks`), su versión, su origen (`PATH`, `gestionada` o `ausente`) y la versión encontrada, sin usar la red.
- `mth tools install <herramienta> [--force]` descarga la herramienta a una caché del usuario (`MTH_TOOLS_DIR` o el directorio de caché del sistema) tras comprobar su SHA-256; `mth tools prune` borra las versiones que ya no están en el manifiesto. No se descarga nada sin esa orden explícita.
- `mth secrets` y `mth doctor` usan `gitleaks` del `PATH` si alcanza la versión mínima y, si no, la copia gestionada. Sin ninguna, el error indica `mth tools install gitleaks`; `mth doctor` informa del origen y avisa de copias gestionadas de otra versión.
