---
bump: minor
refs: SPEC-0028, ADR-0025
---
### Añadido
- Nuevo agente opcional `auditor-ejecucion` y packs `tls` (RFC 9325) y `ssh` (ssh-audit): audita TLS y SSH de servicios en marcha. Su única vía de red es `mth audit scan`, que ejecuta `testssl` o `ssh-audit` solo contra los destinos de la nueva clave `audit.targets` (vacía por defecto; coincidencia exacta, sin comodines), sin shell, con tiempo y salida acotados. Las herramientas las instala quien audita; sin ellas, el control queda `no evaluable`.
