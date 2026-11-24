# ADR-0011 · Adopción: deducir, por defecto o preguntar

- Estado: aceptado
- Fecha: 2026-11-24
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

[ADR-0003](ADR-0003-adopcion-guiada-por-perfiles-de-destino.md) hace que `mth survey` decida qué preguntas hacer según el perfil y las señales detectadas. En una adopción real (repo en GitLab con metodología propia, ~500 ficheros y 42 ADR) la entrevista hizo 12 preguntas en 3 rondas, y la persona rechazó la tercera. Problemas observados:

- **8 de 12 preguntas tenían respuesta deducible** del inventario: la rama de integración (solo existe `dev` y las ramas ya salen de ella), encadenar el hook `commit-msg`, la CI (no hay GitHub), `mth release` (no hay GitHub), el comando de tests (`make test` incluye `pytest`), el idioma (detectado), la escalera de modelos (nada del repo la condiciona) y el modo legado (con ~500 ficheros, "completa" no es viable).
- **Se ofrecían opciones que el propio texto declaraba rotas**: "fallaría en el paso de GitHub", "no aporta nada hoy", "choca con tus bloqueos". Ofrecerlas solo sirve para pedir una confirmación innecesaria.
- **"Sustituir el hook" quitaba controles de seguridad.** PRINCIPLES §2 (fail-safe) dice "denegar, no degradar", así que no debería ser una opción.
- **El orden no respetaba las dependencias.** "¿Qué prevalece, el repo o la metodología?" condiciona la autonomía, la integración y la publicación, y se preguntó en la tercera ronda.
- **No se mostraba el resultado conjunto.** Con esas respuestas, `mth integrate` y `mth release` quedaban fuera, y la persona no lo vio antes de confirmar.
- **Una opción prometía algo sin verificar**: revisores que "solo aplicarían a su área". La capacidad existe (`[review.paths]`), pero la entrevista no tenía forma de registrarla en la respuesta.

Fuerzas: determinismo (§2); proporcionalidad (§12); cada pregunta tiene un coste para la persona; las adaptaciones deben quedar registradas (ADR-0003, punto 4).

## Decisión

1. **Cada pregunta del inventario se resuelve en código** con uno de tres resultados:
   - `deducida`: una señal la resuelve. Lleva un valor y su evidencia (fichero, rama, remoto).
   - `por_defecto`: ninguna señal la condiciona. Se aplica el valor por defecto y se puede cambiar con `mth reconfigure`.
   - `decision`: hay una ventaja y un coste reales que dependen de la persona. Solo estas se preguntan.
2. **Reglas mínimas de deducción** (la spec las concreta y las prueba):
   - Rama de integración: si hay una única candidata (`develop` o `dev`) y todas las ramas de trabajo del remoto salen de ella → esa. Una rama «sale de» la candidata cuando su punto de bifurcación con ella no es ya parte de `main`. Sin ninguna candidata → `por_defecto`: se crea `development`. Con varias candidatas, o sin ramas de trabajo que lo confirmen → `decision`.
   - Hook `commit-msg` ajeno → se encadena siempre. "Sustituir" NO DEBE ofrecerse.
   - CI y publicación: dependen de `forge` ([ADR-0012](ADR-0012-forja-configurable.md), que sustituye a la regla provisional original: un remoto que no era `github.com` desactivaba la CI de la metodología, `mth release` y `mth integrate`). Con `forge` distinto de `github`, `ci` se deduce a `sin-ci` y las capacidades son parciales: `mth` hace la parte local y la persona la de la forja.
   - Comando de tests: si existe un objetivo `test` en `Makefile` o `justfile` → ese, porque es el punto de entrada del proyecto. Otras herramientas equivalentes se añaden cuando el inventario las detecte.
   - Idioma: el detectado, si la detección es inequívoca (`es` o `en`); si no hay texto suficiente → `por_defecto` (`es`).
   - Escalera de modelos → `por_defecto`.
   - Modo legado → gradual en los perfiles `existing`, `methodology` y `fork`.
3. **Solo se ofrece lo que funciona.** Una opción que falla con el inventario detectado NO DEBE ofrecerse: el inventario lista, por pregunta, las opciones ofrecidas, y `mth init --answers` rechaza las demás. El texto de cada opción describe solo comportamiento que existe; un test recorre las opciones y lo que prometen sus textos (comandos de `mth`, claves de configuración) contra las capacidades del plugin.
4. **Orden por dependencia y una sola ronda.** Primero va la precedencia (repo o metodología); después, lo que depende de ella (autonomía) y el resto. El objetivo es un máximo de 4 preguntas de tipo `decision`. Si salen más, se hacen, pero es señal de que falta una regla de deducción.
5. **Resumen antes de escribir.** `mth init --answers` genera, de forma determinista, un plan con cuatro bloques: lo deducido con su evidencia, lo que va por defecto, lo decidido, y las capacidades que quedan activas y desactivadas con su motivo. `mth init --answers --plan` lo muestra sin escribir nada; la skill lo presenta y solo ejecuta la adopción tras la confirmación de la persona. Cualquier valor deducido o por defecto se corrige con una respuesta explícita a esa pregunta.
6. **Registro.** El ADR de adopción del repo destino lista cada pregunta con su resultado (`deducida`, `por_defecto` o `decision`). Esa es la fuente para afinar las reglas: una pregunta que siempre se responde con la recomendada debe pasar a deducirse.

Modifica ADR-0003 (puntos 2 y 3): los textos siguen siendo fijos, pero ya no se hacen todas las preguntas de la base del perfil. `mth reconfigure` ([ADR-0007](ADR-0007-reestructuracion-reutilizando-la-entrevista-de-adopcion.md)) sigue mostrando todas las preguntas con su valor actual.

Detalle en [SPEC-0015](../../features/SPEC-0015-adopcion-deducir-por-defecto-o-preguntar.md).

## Alternativas consideradas

- **Mantener las preguntas y mejorar los textos:** no resuelve el problema; el coste para la persona es el número de preguntas.
- **Que Opus decida qué preguntar:** no es determinista ni se puede probar, y contradice ADR-0003, punto 4.
- **No preguntar nada y aplicar valores por defecto:** la precedencia y los revisores son decisiones reales; imponerlas decide por la persona.
- **Obligar a confirmar el plan en `mth` (por ejemplo, con `--yes`):** cambiaría el contrato de `mth init --answers` sin que la confirmación sea más fiable, porque quien lo ejecuta es la skill. Se separa en `--plan` (solo lee) y la ejecución.

## Consecuencias

- **Positivas:** en el caso observado, 12 preguntas en 3 rondas pasan a 4 en una. La persona ve qué pierde antes de confirmar, y cada deducción queda trazada con su evidencia.
- **Negativas:** hay que mantener las reglas de deducción y sus tests. Una regla mal escrita decide algo equivocado sin preguntar.
- **Riesgo aceptado:** una deducción errónea. Lo mitiga el resumen previo, que permite corregir cualquier valor antes de escribir, y `mth reconfigure`. En concreto, un GitHub Enterprise con otro dominio se detecta como `none` ([ADR-0012](ADR-0012-forja-configurable.md)); el resumen lo muestra y se corrige respondiendo `forja` y `ci`.
