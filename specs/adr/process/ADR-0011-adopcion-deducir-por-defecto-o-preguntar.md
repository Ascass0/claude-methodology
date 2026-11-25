# ADR-0011 · Adopción: deducir, por defecto o preguntar

- Estado: aceptado
- Fecha: 2026-11-24
- Categoría: process
- Formato: compacto

## Contexto

- [ADR-0003](ADR-0003-adopcion-guiada-por-perfiles-de-destino.md): `mth survey` decide las preguntas según perfil y señales. En una adopción real (GitLab, metodología propia, ~500 ficheros, 42 ADR) hizo 12 preguntas en 3 rondas y la persona rechazó la tercera.
- 8 de 12 eran deducibles del inventario: rama de integración (solo existe `dev` y las ramas salen de ella), encadenar `commit-msg`, CI y `mth release` (no hay GitHub), comando de tests (`make test` incluye `pytest`), idioma, escalera de modelos y modo legado (con ~500 ficheros «completa» no es viable).
- Se ofrecían opciones que el propio texto declaraba rotas («fallaría en el paso de GitHub»).
- «Sustituir el hook» quitaba controles de seguridad, contra PRINCIPLES §2 (denegar, no degradar).
- El orden no respetaba dependencias: «¿qué prevalece, repo o metodología?» condiciona autonomía, integración y publicación y se preguntó en la tercera ronda.
- No se mostraba el resultado conjunto: `mth integrate` y `mth release` quedaban fuera sin que la persona lo viera antes de confirmar.
- Una opción prometía revisores que «solo aplicarían a su área» (`[review.paths]`) sin forma de registrarlo en la respuesta.
- Fuerzas: determinismo (§2), proporcionalidad (§12), coste de cada pregunta, adaptaciones registradas (ADR-0003, punto 4).

## Decisión

1. Cada pregunta del inventario DEBE resolverse en código con uno de tres resultados:
   - `deducida`: una señal la resuelve; lleva valor y evidencia (fichero, rama, remoto).
   - `por_defecto`: ninguna señal la condiciona; se aplica el valor por defecto, cambiable con `mth reconfigure`.
   - `decision`: depende de la persona con ventaja y coste reales; solo estas se preguntan.
2. Reglas mínimas de deducción (las concreta y prueba la spec):
   - Rama de integración: una única candidata (`develop` o `dev`) de la que salen todas las ramas de trabajo del remoto → esa (una rama «sale de» la candidata si su punto de bifurcación con ella no es ya parte de `main`). Sin candidata → `por_defecto`: se crea `development`. Varias candidatas, o sin ramas que lo confirmen → `decision`.
   - Hook `commit-msg` ajeno → se encadena siempre; «sustituir» NO DEBE ofrecerse.
   - CI y publicación: dependen de `forge` ([ADR-0012](ADR-0012-forja-configurable.md), que sustituye a la regla provisional original). Con `forge` distinto de `github`, `ci` se deduce a `sin-ci` y las capacidades son parciales.
   - Comando de tests: objetivo `test` de `Makefile` o `justfile` → ese; otras herramientas se añaden cuando el inventario las detecte.
   - Idioma: el detectado si es inequívoco (`es` o `en`); sin texto suficiente → `por_defecto` (`es`).
   - Escalera de modelos → `por_defecto`.
   - Modo legado → gradual en los perfiles `existing`, `methodology` y `fork`.
3. Solo DEBE ofrecerse lo que funciona: el inventario lista por pregunta las opciones ofrecidas y `mth init --answers` rechaza las demás. El texto de cada opción describe solo comportamiento existente; un test contrasta lo que prometen los textos (comandos de `mth`, claves) con las capacidades del plugin.
4. Orden por dependencia y una sola ronda: primero la precedencia (repo o metodología), luego autonomía y el resto. Objetivo: máximo 4 preguntas `decision`; más es señal de una regla de deducción que falta.
5. `mth init --answers` DEBE generar un plan determinista con cuatro bloques (deducido con evidencia, por defecto, decidido, capacidades activas y desactivadas con motivo). `--plan` lo muestra sin escribir; la skill lo presenta y solo ejecuta tras la confirmación. Un valor deducido o por defecto se corrige con una respuesta explícita.
6. El ADR de adopción del destino DEBE listar cada pregunta con su resultado; una pregunta que siempre se responde con la recomendada debe pasar a deducirse.

Modifica ADR-0003 (puntos 2 y 3): los textos siguen fijos, pero ya no se hacen todas las preguntas de la base del perfil. `mth reconfigure` ([ADR-0007](ADR-0007-reestructuracion-reutilizando-la-entrevista-de-adopcion.md)) sigue mostrando todas con su valor actual. Detalle en [SPEC-0015](../../features/SPEC-0015-adopcion-deducir-por-defecto-o-preguntar.md).

## Rechazado

- Mantener las preguntas y mejorar los textos: el coste es el número de preguntas.
- Que Opus decida qué preguntar: no determinista ni probable; contradice ADR-0003, punto 4.
- No preguntar nada: precedencia y revisores son decisiones reales; imponerlas decide por la persona.
- Confirmar el plan en `mth` (`--yes`): cambia el contrato sin hacer la confirmación más fiable, porque quien ejecuta es la skill. Se separa en `--plan` (lee) y la ejecución.

## Consecuencias

- **+** En el caso observado, 12 preguntas en 3 rondas pasan a 4 en una; se ve qué se pierde antes de confirmar y cada deducción queda trazada.
- **−** Hay que mantener las reglas y sus tests; una regla mal escrita decide mal sin preguntar.
- **riesgo** Una deducción errónea → el resumen previo permite corregir antes de escribir, y `mth reconfigure`. Un GitHub Enterprise con otro dominio se detecta como `none` (ADR-0012); se corrige respondiendo `forja` y `ci`.

## Impone

- [script] `mthlib/survey.py` (reglas de deducción, `outcome`), `mthlib/adoption.py` (`--plan`, ADR de adopción con el resultado de cada pregunta).
- [criterio] Test que contrasta las opciones y los textos de `skills/mth-init/preguntas.md` con las capacidades del plugin.
