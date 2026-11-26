# ADR-0012 · Forja configurable

- Estado: aceptado
- Fecha: 2026-11-24
- Categoría: process
- Formato: compacto

## Contexto

- El plugin da por hecho GitHub: `gh` para PR, merges y releases, workflows en `.github/workflows` y estado de la CI desde GitHub.
- En un repo en GitLab: `mth release` falla en el paso de GitHub, la CI de la metodología no corre, `mth doctor` avisa de workflows sin sentido y la entrevista gastaba preguntas (autonomía, CI, publicación) en tapar el hueco. [ADR-0011](ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md) lo resolvió de forma provisional: un remoto que no es `github.com` desactiva `mth integrate` y `mth release`.
- Fail-safe: si `mth` no puede comprobar la CI, no integra como si estuviera en verde.
- Parsimonia: sin soporte completo de una forja sin demanda real. Determinismo: la forja se deduce del remoto.

## Decisión

1. Nueva clave `forge` en `methodology.toml`: `github` | `gitlab` | `none` (por defecto `github`). `mth survey` DEBE deducirla de la URL del remoto con la pregunta `forja`, siempre `deducida` y nunca preguntada: `github.com` → `github`; `gitlab.com` o un host cuya primera etiqueta es `gitlab` → `gitlab`; cualquier otro remoto o ninguno → `none`. Un GitHub Enterprise con otro dominio cae en `none` hasta corregirlo con una respuesta explícita a `forja`. Sustituye a la regla provisional de ADR-0011 (punto 2, «CI y publicación»).
2. Con `github`, el comportamiento NO DEBE cambiar.
3. Con `gitlab` o `none`, `mth` DEBE hacer la parte local y determinista, y la persona la de la forja:
   - `mth integrate`: comprueba los gates locales, sube la rama (git) y prepara título y cuerpo del MR en `.work/merge-request/`. NO DEBE fusionar: sin acceso a la forja no puede comprobar la CI, y fusionar sin ella sería degradar. Muestra la lista exacta de pasos manuales; vuelto a ejecutar tras el merge, detecta la rama integrada y limpia.
   - `mth release`: calcula la versión, genera `CHANGELOG.md` desde los fragmentos, prepara y sube `release/vX.Y.Z` y deja el texto de la release en `.work/merge-request/`. Merge a `main`, tag, release y vuelta a `development` los hace la persona; al reejecutar marca los pasos ya cumplidos (por git) y, con todos, limpia la rama.
   - `mth hotfix finish` NO DEBE soportarse: falla antes de tocar nada y lo dice (fusiona y publica; necesita su propio diseño).
   - NO DEBE generarse CI de la metodología (`ci: crear` solo con `github`); `mth doctor` NO DEBE avisar de workflows ni exigir `gh`; `ci.required` no se evalúa porque `mth` no fusiona.
4. El guard DEBE tratar `glab mr merge` igual que `gh pr merge`: bloquearlo y remitir a `mth`.
5. Fuera de alcance: soporte completo de GitLab (`glab`, pipelines, releases); ADR propio cuando haya demanda.

Modifica ADR-0011 (punto 2). Detalle en [SPEC-0016](../../features/SPEC-0016-forja-configurable.md).

## Rechazado

- Soporte completo de GitLab ahora: duplica la capa de forja sin demanda medida (YAGNI). La decisión 3 deja el punto de extensión: una segunda variante real justifica abstraer (SOLID O).
- Seguir preguntando en la adopción: preguntas con una única respuesta válida.
- Fusionar en GitLab con `git merge` sin comprobar la CI: viola el fail-safe.
- Que `mth release` cree el tag y la vuelta a `development` al detectar el merge: publicaría una versión sin haber visto la CI de ese merge.

## Consecuencias

- **+** El plugin es usable en GitLab y sin forja; la pregunta de CI desaparece de la adopción; `versiones` se deduce (`continuar`) con etiquetas con prefijo y sin herramienta de publicación; nunca se integra sin la CI comprobada.
- **−** En `gitlab` y `none`, integrar y publicar requieren una persona y los hotfix no se cierran con `mth`; dos caminos que mantener en `integrate` y `release`.
- **riesgo** La persona puede publicar sin seguir los pasos de `mth` → `mth trace` y el `CHANGELOG` generado siguen siendo la fuente de verdad.
- **riesgo** Forja mal deducida (GitHub Enterprise) → se ve en el plan previo y se corrige respondiendo `forja`; como la deducción no cambia las demás respuestas, hay que responder también `ci`.

## Impone

- [script] `mthlib/forge.py` (deducción y capacidades), `mthlib/flow.py` (caminos de `integrate` y `release`), `mthlib/guard.py` (`glab mr merge`), `mthlib/survey.py` (pregunta `forja`).
- [criterio] `mth doctor`: sin avisos de GitHub cuando `forge` ≠ `github`.
