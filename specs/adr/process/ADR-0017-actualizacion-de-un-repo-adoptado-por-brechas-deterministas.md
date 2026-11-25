# ADR-0017 · Actualización de un repo adoptado por brechas deterministas

- Estado: aceptado
- Fecha: 2026-11-25
- Categoría: process
- Formato: compacto

## Contexto

- El plugin evoluciona y cada versión puede exigir más a los repos ya adoptados; la adopción ([ADR-0003](ADR-0003-adopcion-guiada-por-perfiles-de-destino.md)) y la reestructuración ([ADR-0007](ADR-0007-reestructuracion-reutilizando-la-entrevista-de-adopcion.md)) parten de decisiones de la persona, no del cambio del plugin.
- Hoy la persona explica a Claude, cada vez, qué se ha añadido y qué hay que traer al repo.
- Determinismo (§2): detectar qué falta es decidible en código; convertir documentos o elegir agentes opcionales no.
- Un repo antiguo puede tener decisiones propias (config, agentes editados): actualizar no puede pisarlas.
- Este repo desarrolla el plugin y se aplica su propia metodología: la operación nace probada sobre él.

## Decisión

1. La actualización DEBE ser una operación propia (`mth update` y la skill `mth-update`), distinta de `mth init` (repo sin adoptar) y de `mth reconfigure` (cambiar decisiones).
2. El diagnóstico DEBE basarse en **brechas** comprobables, no en una versión registrada: cada una con `id`, clase (`automatica`, `decision`, `informativa`), evidencia y acción.
3. `mth update` DEBE aplicar solo las brechas `automatica`, en `chore/update-methodology` con un único commit y un ADR de actualización; NO DEBE modificar ningún valor ya decidido. Reanudar la rama puede añadir otro commit con lo que faltaba y amplía el mismo ADR.
4. Lo que exige criterio (agentes opcionales, agentes editados, conversión de documentos) DEBE conducirlo la skill con aprobación de la persona, en la misma rama.
5. La skill DEBE usarse solo cuando la persona la invoca: el hook de sesión NO DEBE proponerla.
6. Toda spec que añada una exigencia a los repos adoptados DEBE registrar su brecha en la misma rama; `revisor-adr` lo comprueba.
7. Las brechas `informativa` (coste o trabajo de tests) NO DEBEN aplicarse ni bloquear.

## Rechazado

- Registrar en `methodology.toml` la versión del plugin aplicada: añade una clave que un plugin antiguo rechaza (SPEC-0009), se desfasa si alguien edita a mano y no dice qué falta; las brechas sí.
- Ampliar `mth reconfigure`: mezcla «cambiar una decisión mía» con «traer lo nuevo del plugin»; precondiciones y registro distintos.
- Proponer la actualización al abrir una sesión: decisión de la persona; solo bajo invocación.
- Aplicarlo todo en `mth update`, incluida la conversión de documentos: decide por la persona y produce un PR irrevisable.
- Que Opus detecte el desfase leyendo el repo: no determinista ni probable.

## Consecuencias

- **+** La persona no vuelve a explicar el proceso; lo nuevo del plugin llega con un PR revisable y un ADR.
- **+** Idempotente y reanudable: sin brechas, «al día».
- **−** Cada exigencia nueva del plugin cuesta registrar su brecha; es una regla más que revisar.
- **riesgo** Una exigencia sin brecha registrada no se detecta → `revisor-adr` lo comprueba en cada diff que toque specs de adopción o configuración.
- **riesgo** Una brecha `automatica` mal clasificada pisa algo → solo se aplica lo que no cambia valores existentes; el resto pasa a `decision`.

## Impone

- [script] `mthlib/update.py` (registro de brechas, `mth update --plan`, `mth update`) y su test del registro.
- [criterio] `revisor-adr` (sección local de este repo): toda spec que añada una exigencia a repos adoptados registra su brecha.
- [criterio] Skill `mth-update`: sin disparo automático; el hook de sesión no la propone.
