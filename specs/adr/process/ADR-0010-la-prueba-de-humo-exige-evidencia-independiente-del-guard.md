# ADR-0010 · La prueba de humo exige evidencia independiente del guard

- Estado: aceptado
- Fecha: 2026-11-23
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

El guard por agente depende de un comportamiento de Claude Code que no controlamos: que los hooks de `.claude/settings.json` reciban `agent_id` y `agent_type` en las llamadas de los subagentes ([ADR-0008](ADR-0008-catalogo-de-plantillas-de-agentes.md)). La primera prueba real ya refutó un supuesto (los hooks del frontmatter no se aplican a los subagentes). Si una versión futura cambia ese comportamiento, el guard pasa a fallar abierto sin que nada lo avise: un agente «de solo lectura» escribe. Hasta ahora la comprobación era un procedimiento manual de `docs/catalogo-de-agentes.md`, que depende de que alguien se acuerde de repetirlo.

Automatizarla tiene una trampa: en modo no interactivo, el sistema de permisos de Claude Code también puede impedir un comando. Una prueba que se limite a observar que el comando «no se ejecutó» da un falso positivo cuando lo impidió el sistema de permisos y no el guard. Además, la prueba depende de la CLI `claude`, de autenticación y de red, y gasta tokens: puede no llegar a concluir.

## Decisión

`mth smoke` ejecuta un subagente canario en un repositorio temporal y exige **evidencia independiente del propio guard**, con tres resultados: pasa, falla y no concluyente.

1. **Pasa** solo si coinciden: el registro del guard muestra una llamada a `Bash` del canario con `agent_type` bloqueada; el registro muestra una llamada a `Write` del mismo canario **permitida** (control positivo) y su efecto existe en disco; y el comando bloqueado no dejó efecto alguno. El control positivo demuestra que el subagente usa herramientas y que el hook está en su camino.
2. **Falla** si hay prueba de que el guard no actuó: el efecto del comando bloqueado existe, o el efecto del control positivo existe sin una decisión del guard que lo respalde.
3. **No concluyente** en cualquier otro caso (sin `claude`, sin autenticación o red, plazo agotado, el modelo no llamó a la herramienta, el sistema de permisos lo impidió). Un resultado no concluyente nunca registra la versión.
4. La prueba corre en un repositorio temporal con su propio `.claude/settings.json`, con solo las fuentes de configuración del proyecto, y se limpia en todos los caminos. Usa un modelo barato fijo, un máximo de turnos, un tope de coste y un plazo.
5. Al pasar, `mth` registra la salida de `claude --version` en `<git-common-dir>/mth/smoke`; `mth session` y `mth doctor` avisan cuando la versión de Claude Code que se usa difiere de la registrada. Un fallo borra el registro.

Detalle en [SPEC-0014](../../features/SPEC-0014-prueba-de-humo-de-los-agentes.md).

## Alternativas consideradas

- **Seguir con el procedimiento manual:** depende de la memoria de quien actualiza Claude Code; es el estado del que partimos.
- **Una lista de versiones permitidas:** registra qué versiones conocemos, no verifica comportamiento; dos versiones iguales de fuera pueden comportarse distinto por configuración.
- **Considerar que pasa si el comando no se ejecutó:** falso positivo cuando lo bloquea el sistema de permisos.
- **Leer la transcripción de la sesión:** depende de un formato no documentado y no prueba que el hook se ejecutó.
- **Ejecutarla en CI en cada cambio:** requiere credenciales y gasta tokens en cada commit; se deja como decisión de quien opera el repo.

## Consecuencias

- El riesgo del ADR-0008 pasa de «cuando alguien se acuerde» a «mth lo avisa cuando la versión cambia».
- Cada prueba cuesta una llamada barata a un modelo y depende de la red: puede ser no concluyente, y no hay que tratarlo como un fallo ni como un pase.
- La prueba verifica un canario, no cada agente: comprueba que el mecanismo (hook, `agent_type`, guard) funciona, no las reglas de cada plantilla (eso lo cubren los casos `[[guard]]`).
- Riesgo aceptado: un cambio de Claude Code que solo afecte a un tipo de herramienta no probado (por ejemplo `Edit`) no se detecta; el canario ejerce `Bash` y `Write`.
