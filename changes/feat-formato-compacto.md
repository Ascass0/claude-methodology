---
bump: minor
refs: SPEC-0018, ADR-0014
---
### Añadido
- Formato compacto de specs y ADR: las plantillas (español e inglés) llevan la línea `- Formato: compacto`, criterios de aceptación en EARS (`CUANDO … DEBE …`, `SI … ENTONCES …`, `MIENTRAS …`), modos de fallo con ID `FM-NN` y ADR con campos fijos (`Contexto`, `Decisión`, `Rechazado`, `Consecuencias`, `Impone`).
- `mth trace` valida ese formato en los documentos que lo declaran y comprueba las referencias `SPEC-NNNN/FM-NN`. Los specs y ADR existentes no cambian.

### Cambiado
- `context/core.md`, `PRINCIPLES.md`, el bloque de `CLAUDE.md` y las descripciones de skills y agentes se reescriben en estilo compacto, sin perder ninguna regla: −13 % de tokens estimados en lo que se carga siempre (2,8 k → 2,4 k) y −11 % contando `PRINCIPLES.md` (8,5 k → 7,5 k).
- `PRINCIPLES.md` §7 fija el estilo compacto y `revisor-adr` revisa que los documentos compactos lo cumplan.
