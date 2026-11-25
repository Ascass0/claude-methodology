# ADR-0013 · Decisión autónoma de versión

- Estado: aceptado
- Fecha: 2026-11-24
- Categoría: process
- Formato: compacto

## Contexto

- La metodología integra de forma autónoma, pero publicar quedaba en manos de la persona: nada decía si un cambio merece versión ni de qué nivel.
- El nivel lo escribía quien creaba la rama (`bump` del fragmento: `minor` para `feat`, `patch` para `fix`) y nadie comprobaba su coherencia: se publicaba por cada merge o nunca, con niveles discutibles (una feature como patch, una eliminación como patch).
- SemVer 2.0: el nivel lo da el efecto sobre quien usa el proyecto, no el esfuerzo.
- Determinismo (§2): lo decidible en código no se deja al juicio del agente.
- Fail-safe: publicar es saliente y difícil de deshacer; `1.0.0` declara una API estable, decisión de la persona.

## Decisión

1. `mth release --plan` (solo lee) DEBE imprimir los fragmentos con su nivel, el nivel resultante, la versión propuesta y una recomendación con motivos: `publicar`, `esperar`, `no publicar` o `bloqueado`.
2. Solo lo que tiene fragmento merece versión. El mantenimiento sin fragmento (docs, CI, tests, refactor sin cambio de comportamiento) NO DEBE versionar por sí solo: se acumula hasta la siguiente versión con fragmentos.
3. El nivel DEBE ser el mayor entre los fragmentos, con un mínimo por fragmento que `mth` comprueba al integrar y al publicar:
   - `feat`: al menos `minor`.
   - `fix`, `hotfix`, `security`: al menos `patch` (un hotfix sigue siendo `patch`).
   - Sección de eliminaciones (`Eliminado` / `Removed`): al menos `minor` antes de `1.0.0` y `major` desde `1.0.0`.
   - Un `bump` por debajo del mínimo es un error; por encima, se respeta.
4. `1.0.0` NO DEBE publicarse solo: mientras la última versión sea menor que `1.0.0`, un nivel `major` es `bloqueado` y `mth release` lo rechaza salvo `--allow-major` (decisión explícita de la persona).
5. La recomendación DEBE ser `esperar` si hay ramas abiertas que aportan fragmento (`feat`, `fix`, `hotfix` en el remoto): es recomendación, no bloqueo. Con `autonomy.level = full`, tras cada integración en `development` el agente ejecuta `mth release --plan` y publica si recomienda `publicar`; con `until-pr` o `supervised`, el guard pide confirmación antes de publicar.
6. `mth release --plan` y la publicación DEBEN dejar la decisión y sus motivos en la traza (`release.plan`).

Detalle en [SPEC-0017](../../features/SPEC-0017-decision-autonoma-de-version.md).

## Rechazado

- Publicar siempre que haya un fragmento: no impide un nivel incoherente ni cruzar `1.0.0` sin querer.
- Que el agente decida el nivel por su cuenta: no determinista ni probable; el mínimo por tipo sí, y deja el juicio donde hace falta (`major`, `esperar`).
- Calcular el nivel desde los commits (Conventional Commits): los fragmentos ya son la fuente del changelog; dos verdades.
- Bloquear siempre con ramas abiertas: impediría publicar un fix mientras una feature larga sigue abierta.

## Consecuencias

- **+** «¿0.10.1 o 0.11.0?» se responde en código y con motivos; nunca una versión de nivel incoherente ni `1.0.0` por accidente; el mantenimiento no genera versiones vacías.
- **−** Un `bump` por debajo del mínimo rechaza la integración hasta corregir el fragmento; una regla más que mantener.
- **riesgo** El mínimo por tipo no detecta un `fix` o `feat` que rompe compatibilidad sin eliminar nada (cambio de significado de una opción) → lo declara quien escribe el fragmento (`bump` mayor) o la revisión.

## Impone

- [script] `mthlib/releaseplan.py` (`mth release --plan`, recomendación), `mthlib/changelog.py` (mínimo por fragmento), `--allow-major` en `mth release`.
- [criterio] `mth integrate` y `mth release`: rechazan un `bump` por debajo del mínimo de su tipo.
