# ADR-0010 · La prueba de humo exige evidencia independiente del guard

- Estado: aceptado
- Fecha: 2026-11-23
- Categoría: process
- Formato: compacto

## Contexto

- El guard por agente depende de algo que no controlamos: que los hooks de `.claude/settings.json` reciban `agent_id` y `agent_type` en las llamadas de subagentes ([ADR-0008](ADR-0008-catalogo-de-plantillas-de-agentes.md)). La primera prueba real ya refutó un supuesto.
- Si una versión cambia ese comportamiento, el guard falla abierto sin aviso: un agente «de solo lectura» escribe.
- La comprobación era un procedimiento manual de `docs/catalogo-de-agentes.md`, que depende de que alguien se acuerde.
- Trampa al automatizar: en modo no interactivo el sistema de permisos de Claude Code también puede impedir un comando; «no se ejecutó» da un falso positivo si lo impidió ese sistema y no el guard.
- Depende de la CLI `claude`, autenticación y red, y gasta tokens: puede no concluir.

## Decisión

`mth smoke` DEBE ejecutar un subagente canario en un repositorio temporal y exigir **evidencia independiente del propio guard**, con tres resultados:

1. **Pasa** solo si coinciden: el registro del guard muestra una llamada `Bash` del canario con `agent_type` bloqueada; muestra una llamada `Write` del mismo canario permitida (control positivo) con su efecto en disco; y el comando bloqueado no dejó efecto.
2. **Falla** si hay prueba de que el guard no actuó: existe el efecto del comando bloqueado, o el del control positivo sin una decisión del guard que lo respalde.
3. **No concluyente** en cualquier otro caso (sin `claude`, sin autenticación o red, plazo agotado, el modelo no llamó a la herramienta, lo impidió el sistema de permisos). NO DEBE registrar la versión.
4. La prueba DEBE correr en un repositorio temporal con su propio `.claude/settings.json` y solo las fuentes de configuración del proyecto, limpiarse en todos los caminos y usar un modelo barato fijo, máximo de turnos, tope de coste y plazo.
5. Al pasar, `mth` DEBE registrar la salida de `claude --version` en `<git-common-dir>/mth/smoke`; `mth session` y `mth doctor` DEBEN avisar si la versión en uso difiere. Un fallo DEBE borrar el registro.

Detalle en [SPEC-0014](../../features/SPEC-0014-prueba-de-humo-de-los-agentes.md).

## Rechazado

- Procedimiento manual: depende de la memoria de quien actualiza Claude Code.
- Lista de versiones permitidas: registra versiones conocidas, no verifica comportamiento.
- Dar por pasada la prueba si el comando no se ejecutó: falso positivo cuando lo bloquea el sistema de permisos.
- Leer la transcripción de la sesión: formato no documentado y no prueba que el hook se ejecutó.
- Ejecutarla en CI en cada cambio: credenciales y tokens en cada commit; lo decide quien opera el repo.

## Consecuencias

- **+** El riesgo del ADR-0008 pasa de «cuando alguien se acuerde» a «mth avisa cuando la versión cambia».
- **−** Cada prueba cuesta una llamada barata y depende de la red: puede ser no concluyente, y no es ni fallo ni pase.
- **−** Verifica un canario, no cada agente: el mecanismo (hook, `agent_type`, guard), no las reglas de cada plantilla (las cubren los casos `[[guard]]`).
- **riesgo** Un cambio que solo afecte a una herramienta no probada (`Edit`) no se detecta; el canario ejerce `Bash` y `Write`.

## Impone

- [script] `mthlib/smoke.py` (`mth smoke`, registro de versión); `mthlib/session.py` y `mth doctor` avisan al cambiar la versión.
- [criterio] Se repite al actualizar Claude Code y antes de cada versión del plugin (ADR-0008).
