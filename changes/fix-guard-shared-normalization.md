---
bump: patch
refs: SPEC-0007, SPEC-0016
---
### Corregido
- **Guard**: la petición de confirmación del nivel de autonomía (`until-pr`, `supervised`) ve ahora los mismos comandos que el bloqueo: con prefijos (`sudo git push`), agrupaciones de shell (`(git commit …)`) y continuaciones de línea. El bloqueo de merges a mano también cubre `$(gh pr merge …)` al inicio de un comando, y el guard bloquea los comandos `glab` y los lanzados en segundo plano con `&`. Un fallo interno del guard indica ahora el tipo de excepción.
