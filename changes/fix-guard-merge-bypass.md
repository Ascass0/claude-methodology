---
bump: patch
refs: SPEC-0016
---
### Corregido
- **Guard**: el bloqueo de los merges a mano ya no se esquiva con opciones globales (`gh -R owner/repo pr merge`), con un prefijo como `sudo` o `env`, ni con una escritura de `gh api` / `glab api` a un endpoint `…/merge`. Los merges siguen haciéndose con `mth integrate`, `mth release` o `mth hotfix finish`.
