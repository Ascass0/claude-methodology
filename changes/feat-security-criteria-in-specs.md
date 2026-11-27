---
bump: minor
refs: SPEC-0026
---
### Añadido
- Las specs compactas pueden declarar su superficie de seguridad con la cabecera `- Seguridad:` (`ninguna`, o `entrada externa`, `autenticación`, `datos sensibles`). Con superficie declarada, `mth trace` exige al menos un criterio de seguridad con la etiqueta `[SEG]` (`[SEC]` en inglés) y su test. Las specs sin la cabecera no cambian.
- Las plantillas de spec llevan `- Seguridad: ninguna`, la skill `mth-spec` lo explica y `revisor-seguridad` (1.2.0) contrasta la superficie declarada con el diff.
