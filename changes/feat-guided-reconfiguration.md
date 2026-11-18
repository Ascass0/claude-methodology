---
bump: minor
refs: SPEC-0011, ADR-0007
---
### Añadido
- Skill `mth-reconfigure`: en un repo ya adoptado, vuelve a pasar la entrevista de la adopción. Se puede rehacer el formulario completo, revisar bloques (`flujo`, `documentacion`, `calidad`, `agente`) o cambiar solo una decisión.
- `mth survey --reconfigure [--only …]`: inventario de un repo adoptado con cada pregunta aplicable y su valor actual.
- `mth reconfigure --answers FICHERO [--only …]`: valida las respuestas y las aplica sobre la configuración actual, conservando lo que no se pregunta. Abre `chore/reconfigure-methodology` con la configuración nueva y un ADR de reestructuración que lista cada clave que cambia. Si las respuestas no cambian nada, o no se pueden aplicar, no crea nada.
- Con `autonomy.level = "supervised"`, el guard pide confirmación para `mth reconfigure`.
