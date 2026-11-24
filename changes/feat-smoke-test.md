---
bump: minor
refs: SPEC-0014, ADR-0010
---
### Añadido
- `mth smoke` comprueba con el Claude Code real que el guard de los agentes bloquea: lanza un subagente canario en un repositorio temporal y da tres resultados (pasa, falla, no concluyente). Pasa solo si el registro del guard muestra el comando del canario bloqueado y una escritura permitida (control positivo) que sí se ejecutó, y el comando prohibido no dejó efecto; que el comando no se ejecutara no basta, porque el sistema de permisos también puede impedirlo. No toca el repo desde el que se lanza, limpia siempre, y acota el coste (modelo `haiku`, 8 turnos, 0,5 USD, 180 s). (SPEC-0014, ADR-0010)
- Al pasar, registra la versión de Claude Code que se probó. Con agentes del catálogo instalados, `mth session` y `mth doctor` avisan si no hay registro o si Claude Code ha cambiado desde la última prueba de humo. (SPEC-0014)
- La redacción de credenciales de los registros del guard y de `mth smoke` cubre también los usuarios y claves de una URL (`https://usuario:clave@host`) y los `Bearer` sueltos. (SPEC-0014)
