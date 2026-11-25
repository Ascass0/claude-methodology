---
bump: patch
refs: SPEC-0012
---
### Corregido
- **Catálogo de agentes**: los agentes, los guards y el shim que instala `mth agents add` ya no citan specs ni ADR internos del plugin (SPEC-0012, ADR-0008, ADR-0015…). Un repo adoptado no los define, así que `mth trace` fallaba y bloqueaba su integración. Si ya tienes agentes instalados, `mth agents sync` los actualiza.
