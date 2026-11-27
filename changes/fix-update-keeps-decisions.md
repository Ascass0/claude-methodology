---
bump: patch
refs: SPEC-0021, ADR-0017
---
### Corregido
- `mth update` ya no borra lo que anotaste en el ADR de actualización al volver a ejecutarse en `chore/update-methodology`: solo amplía la lista de brechas aplicadas, añade los pendientes nuevos y conserva tus decisiones y el resto del documento. Si el ADR ya no tiene la estructura generada, se detiene sin tocarlo para no perder lo que escribiste.
