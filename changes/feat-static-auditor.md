---
bump: minor
refs: SPEC-0027, ADR-0024
---
### Añadido
- `mth audit packs` lista los packs de línea base del auditor (`comun`, `docker` y `kubernetes`: versión, controles, fecha de revisión, vigencia y hash) y `mth audit verify` con el informe valida un informe contra su pack: solo controles reales, resultado con evidencia para los mínimos, versión y hash coincidentes, y nunca «certificado». `mth doctor` avisa de packs caducados cuando el auditor está instalado.
- Nuevo agente opcional `auditor-estatico` (catálogo) y skill `mth-audit`: auditan un dominio contra su pack con herramientas offline, solo lectura y escribiendo únicamente en `.work/security-report/`. Sin la herramienta, el control queda `no evaluable`.
