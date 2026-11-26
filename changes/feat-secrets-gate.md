---
bump: minor
refs: SPEC-0022
---
### Añadido
- Gate de secretos en el historial: con `secrets.mode = "block"`, `mth integrate` escanea con `gitleaks` los commits de la rama antes de subirla y bloquea ante un hallazgo nuevo. Los hallazgos se muestran sin el valor del secreto y el informe temporal se borra siempre.
- `mth secrets` escanea la rama o, con `--history`, todo el historial; `--history --accept` acepta los hallazgos ya existentes en una línea base (`secrets.baseline`) y recuerda que hay que rotarlos.
- `mth update --plan` señala la brecha `secretos` (decisión) mientras `secrets.mode` esté sin decidir; `mth doctor` avisa del modo y de la falta de `gitleaks`. Nunca se activa en silencio.
- `revisor-seguridad` 1.1.0 vigila los cambios de `secrets.mode` y de la línea base.
