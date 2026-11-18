---
bump: patch
refs: SPEC-0001, SPEC-0002
---
### Corregido
- El plugin declara su versión real (0.5.1) en `plugin.json`, en el marketplace y en `mth --version`. La 0.5.0 se publicó declarando 0.4.0, así que Claude Code no ofrecía la actualización a quien ya tenía instalado el plugin: actualiza para recibir los cambios de la 0.5.0.
- El CHANGELOG incluye la sección de la 0.5.0 (delegación verificable y niveles de modelo), que faltaba.
