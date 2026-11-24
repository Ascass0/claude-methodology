# ADR-0012 · Forja configurable

- Estado: aceptado
- Fecha: 2026-11-24
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

El plugin da por hecho GitHub: `gh` para PR, merges y releases, workflows en `.github/workflows` y el estado de la CI leído desde GitHub. En un repo alojado en GitLab:

- `mth release` falla en el paso de GitHub;
- la CI de la metodología no se ejecuta;
- `mth doctor` avisa de que faltan workflows de GitHub, que no tienen sentido;
- la entrevista de adopción gastó preguntas (autonomía, CI y publicación) en tapar este hueco. [ADR-0011](ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md) lo resolvió de forma provisional: un remoto que no es `github.com` desactiva `mth integrate` y `mth release`.

Fuerzas: fail-safe ("denegar, no degradar"): si `mth` no puede comprobar la CI, no puede integrar como si estuviera en verde. Parsimonia: no se construye soporte completo para una forja sin demanda real. Determinismo: la forja se deduce del remoto.

## Decisión

1. **Nueva clave `forge` en `methodology.toml`:** `github` | `gitlab` | `none` (por defecto `github`, así que los repos adoptados no cambian). `mth survey` la deduce de la URL del remoto con una pregunta nueva, `forja`, siempre `deducida` (ADR-0011) y nunca preguntada: `github.com` → `github`; `gitlab.com`, o un host cuya primera etiqueta es `gitlab` → `gitlab`; cualquier otro remoto o ninguno → `none`. Un GitHub Enterprise con otro dominio cae en `none` hasta que se corrija con una respuesta explícita a `forja`. Esta clave sustituye a la regla provisional del ADR-0011 (punto 2, «CI y publicación»).
2. **Con `github`, el comportamiento no cambia.**
3. **Con `gitlab` o `none`, `mth` hace la parte local y determinista, y la persona hace la parte de la forja:**
   - `mth integrate`: comprueba los gates locales (tests, trazabilidad, revisiones, mensajes), sube la rama (git, no la forja) y prepara el título y el cuerpo del MR en `.work/merge-request/`. No fusiona: sin acceso a la forja no puede comprobar la CI, y fusionar sin ella sería degradar. Al terminar muestra la lista exacta de pasos manuales. Si se vuelve a ejecutar tras el merge, detecta que la rama ya está integrada y limpia.
   - `mth release`: calcula la versión, genera el `CHANGELOG.md` desde los fragmentos, prepara y sube la rama `release/vX.Y.Z` y deja el texto de la release en `.work/merge-request/`. El merge a `main`, el tag, la release y la vuelta a `development` los hace la persona. Al terminar muestra la lista exacta de pasos manuales pendientes; al volver a ejecutarlo marca los que ya se cumplen (por git) y, cuando están todos, limpia la rama.
   - `mth hotfix finish` **no se soporta** con `gitlab` o `none`: falla antes de tocar nada y lo dice. Fusiona y publica, así que necesita su propio diseño.
   - No se genera CI de la metodología (`ci: crear` solo se ofrece con `github`), y `mth doctor` no avisa de que faltan workflows ni exige `gh`. `ci.required` no se evalúa: `mth` no fusiona.
4. **El guard trata `glab mr merge` igual que `gh pr merge`**: lo bloquea y remite a `mth`. Coste mínimo, y mantiene la regla "nada de git a mano" con independencia de la forja.
5. **Fuera de alcance:** soporte completo de GitLab (`glab`, estado de los pipelines, releases). Se abrirá un ADR propio cuando haya demanda.

Modifica [ADR-0011](ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md) (punto 2, CI y publicación). Detalle en [SPEC-0016](../../features/SPEC-0016-forja-configurable.md).

## Alternativas consideradas

- **Soporte completo de GitLab ahora:** duplica la capa de forja sin demanda medida (YAGNI). La decisión 3 deja preparado el punto de extensión: una segunda variante real justifica abstraer (SOLID O).
- **Seguir preguntando en la adopción:** es lo que falla hoy; son preguntas con una única respuesta válida.
- **Fusionar en GitLab con `git merge` sin comprobar la CI:** viola el fail-safe.
- **Que `mth release` cree el tag y la vuelta a `development` al detectar el merge:** acorta los pasos manuales, pero publicaría una versión sin que `mth` haya visto la CI de ese merge. Se deja a la persona.

## Consecuencias

- **Positivas:** el plugin es usable en GitLab y en repos sin forja, la pregunta de CI desaparece de la adopción y `versiones` se deduce (`continuar`) cuando hay etiquetas con prefijo y ninguna herramienta de publicación; en otro caso se sigue preguntando, porque `mth release` funciona en su parte local. Nunca se integra sin la CI comprobada.
- **Negativas:** en `gitlab` y `none`, integrar y publicar requieren una persona, y los hotfix no se pueden cerrar con `mth`. Hay que mantener dos caminos en `integrate` y `release`.
- **Riesgo aceptado:** la persona puede publicar sin seguir los pasos que propone `mth`. `mth trace` y el `CHANGELOG` generado siguen siendo la fuente de verdad. Una forja mal deducida (GitHub Enterprise) se ve en el plan previo de la adopción y se corrige con una respuesta a `forja`; la deducción no cambia las demás respuestas, así que quien corrija `forja` debe responder también `ci`.
