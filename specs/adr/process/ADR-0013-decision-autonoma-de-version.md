# ADR-0013 · Decisión autónoma de versión

- Estado: aceptado
- Fecha: 2026-11-24
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

La metodología integra de forma autónoma, pero la publicación de versiones quedaba en manos de la persona: nada decía si un cambio merece versión ni de qué nivel. El nivel lo escribía quien creaba la rama (`bump` del fragmento, por defecto `minor` para `feat` y `patch` para `fix`) y nadie comprobaba que fuera coherente. Eso lleva a dos errores opuestos: publicar por cada merge, o no publicar nunca; y a niveles discutibles (una feature como patch, o una eliminación de funcionalidad como patch).

Fuerzas: SemVer 2.0 (el nivel lo da el efecto sobre quien usa el proyecto, no el esfuerzo); determinismo (PRINCIPLES §2: lo decidible en código no se deja al juicio del agente); fail-safe: publicar es saliente y difícil de deshacer, y `1.0.0` declara una API estable, que es una decisión de la persona.

## Decisión

1. **La decisión de publicar y de su nivel la toma `mth`, de forma determinista, a partir de los fragmentos.** `mth release --plan` (solo lee) imprime los fragmentos con su nivel, el nivel resultante, la versión propuesta y una recomendación con sus motivos: `publicar`, `esperar`, `no publicar` o `bloqueado`.
2. **Qué merece versión:** solo lo que tiene fragmento, es decir, lo que cambia lo que ve quien usa el proyecto. El mantenimiento sin fragmento (docs, CI, tests, refactor sin cambio de comportamiento) nunca versiona por sí solo: se acumula hasta la siguiente versión con fragmentos.
3. **Nivel (SemVer 2.0):** el mayor entre los fragmentos, con un mínimo por fragmento que `mth` comprueba al integrar y al publicar:
   - `feat`: al menos `minor` (comportamiento nuevo compatible).
   - `fix`, `hotfix`, `security`: al menos `patch`. Un hotfix sigue siendo solo `patch`.
   - Un fragmento con la sección de eliminaciones (`Eliminado` / `Removed`): al menos `minor` antes de `1.0.0` (en `0.y.z` un cambio incompatible sube `minor`) y `major` desde `1.0.0`.
   Un `bump` declarado por debajo del mínimo es un error; por encima, se respeta.
4. **`1.0.0` no se publica solo.** Mientras la última versión sea menor que `1.0.0`, un nivel `major` resultante es `bloqueado`: `mth release` lo rechaza salvo `--allow-major`, que es la decisión explícita de la persona de declarar la API estable.
5. **Cuándo:** la recomendación es `esperar` si hay ramas de trabajo abiertas que aportan fragmento (`feat`, `fix`, `hotfix` en el remoto), porque su contenido puede deber entrar en esta versión; es una recomendación, no un bloqueo. Con `autonomy.level = full`, tras cada integración en `development` el agente ejecuta `mth release --plan` y publica cuando recomienda `publicar`; con `until-pr` o `supervised`, el guard ya pide confirmación antes de publicar.
6. **Registro:** `mth release --plan` y la publicación dejan la decisión y sus motivos en la traza (`release.plan`).

## Alternativas consideradas

- **Publicar siempre que haya un fragmento, sin más criterio:** es lo que ya permitía `mth release`, pero no impide un nivel incoherente ni cruzar `1.0.0` sin querer.
- **Que el agente decida el nivel por su cuenta al publicar:** no es determinista ni se puede probar; la coherencia mínima por tipo sí, y deja el juicio donde hace falta (`major`, `esperar`).
- **Calcular el nivel a partir de los commits (Conventional Commits):** los fragmentos ya son la fuente del changelog; duplicar la fuente crearía dos verdades.
- **Bloquear siempre con ramas abiertas:** impediría publicar un fix mientras una feature larga sigue abierta.

## Consecuencias

- **Positivas:** la pregunta «¿0.10.1 o 0.11.0?» se responde en código y con motivos; nunca se publica una versión de nivel incoherente ni `1.0.0` por accidente; el mantenimiento no genera versiones vacías.
- **Negativas:** quien declare un `bump` por debajo del mínimo ve rechazada su integración y debe corregir el fragmento; hay una regla más que mantener.
- **Riesgo aceptado:** el mínimo por tipo no detecta un `fix` o un `feat` que en realidad rompe compatibilidad sin eliminar nada (por ejemplo, un cambio de significado de una opción): eso lo declara quien escribe el fragmento (`bump` mayor) o la revisión.
