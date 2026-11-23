# Catálogo de preguntas de la adopción

Cada sección es una pregunta de `mth survey`, con su ID. Los textos son fijos para que la metodología se presente siempre igual: sustituye solo los `{…}` por lo que diga el inventario. Cada pregunta se hace con `AskUserQuestion`, en rondas de hasta cuatro: `question` es el texto de **Pregunta** (contexto, evidencia y pregunta en el mismo texto, porque el diálogo puede tapar lo demás), `header` es la **Cabecera**, y cada opción lleva su etiqueta, su descripción y, si la tiene, su vista previa. La primera opción es la recomendada. La persona siempre puede elegir "Otro".

La **Respuesta** es lo que escribes en `answers.<id>` del JSON para `mth init --answers`. Para "Otro", traduce lo que diga la persona a claves de `methodology.toml` (`{"option": "otro", "config": {…}, "note": "<sus palabras>"}`). Si no se puede expresar como configuración, explícale qué opción se acerca más y vuelve a preguntar.

## `alcance`

**Cabecera:** Adopción

**Pregunta:** La metodología exige que todo el trabajo esté trazado: specs con ID, criterios de aceptación con test y enlaces válidos. Tu repo ya tiene {N ficheros, specs o docs} creados sin esas reglas. ¿Cómo quieres adoptarla?

- **Gradual (Recomendado)**: lo existente queda como legado, visible como deuda pero sin bloquear, y lo nuevo o lo que se toque cumple todas las reglas. Vista previa: `mth trace → ⚠ 41 hallazgos en contenido legado · ✓ 0 errores`. Respuesta: `{"option": "gradual"}`
- **Completa**: todo cumple desde el primer día; no se integra nada hasta trazar lo existente. Vista previa: `mth trace → ✗ 41 hallazgos`. Respuesta: `{"option": "completa"}`

Si la persona no quiere adoptar, no es una respuesta: ejecuta `mth init --decline` y termina.

## `ramas`

**Cabecera:** Ramas

**Pregunta:** La metodología separa `main` (solo versiones publicadas) de `development` (lo integrado y aún no publicado): las ramas de trabajo salen de `development` y una versión pasa de `development` a `main`, así que `main` siempre es una versión. En tu remoto {hay `develop` / solo hay `main`}. ¿Qué rama hace de `development`?

- **Usar `{develop}` (Recomendado si existe)**: tu rama de integración hace de `development`; el CI y las protecciones siguen igual. Vista previa: `feat/x → {develop} → main (v1.4.0)`. Respuesta: `{"option": "usar", "branch": "{develop}"}`
- **Crear `development`**: rama nueva desde `main`; habrá que ajustar CI y protecciones a ese nombre. Vista previa: `feat/x → development → main`. Respuesta: `{"option": "crear"}`

## `commits`

**Cabecera:** Commits

**Pregunta:** La metodología valida cada mensaje de commit con Conventional Commits y un trailer `Refs:` que enlaza la spec o el ADR; así el changelog y la trazabilidad salen solos. Tu repo tiene {un hook commit-msg propio / husky / commitlint}. ¿Qué hacemos con él?

- **Sustituirlo (Recomendado si solo valida el formato)**: se guarda como `commit-msg.pre-mth` y se instala el de la metodología. Vista previa: `feat(auth): add token refresh ↵ Refs: SPEC-NNNN`. Respuesta: `{"option": "sustituir"}`
- **Encadenarlo**: se guarda como `commit-msg.local` y se ejecuta antes del de la metodología; el commit debe pasar los dos. Vista previa: `commit-msg → commit-msg.local → mth check-msg`. Respuesta: `{"option": "encadenar"}`

Con un gestor de hooks (husky, lefthook, pre-commit) ninguna de las dos se aplica sola: tras adoptar, añade `mth check-msg "$1"` a su hook commit-msg en la rama de adopción y díselo a la persona. La historia previa nunca se reescribe ni se valida.

## `versiones`

**Cabecera:** Versiones

**Pregunta:** La metodología publica con `mth release`: fusiona `development` en `main`, crea una etiqueta SemVer, genera el CHANGELOG desde los fragmentos de cada rama y actualiza los ficheros que declaran la versión. Tu repo {tiene etiquetas `{v1.3.2}` / usa {release-please} / declara la versión en {package.json}}. ¿Cómo seguimos?

- **Continuar con `mth release` (Recomendado)**: sigue tu numeración y tu prefijo; el CHANGELOG actual se conserva debajo. Vista previa: `{v1.3.2} → v1.4.0 · changes/feat-x.md → ## [1.4.0]`. Respuesta: `{"option": "continuar", "version_files": [{"path": "package.json", "pattern": "\"version\":\\s*\"(\\d+\\.\\d+\\.\\d+)\""}]}` (los `version_files` que detectó el inventario, o ninguno)
- **Prefijo nuevo**: para numeraciones que no son SemVer o etiquetas sin prefijo. Vista previa: `tag_prefix = "r" → r1.0.0`. Respuesta: `{"option": "prefijo", "tag_prefix": "r"}`

Publicar con otra herramienta no está soportado: si la persona lo pide, explícale que `mth release` sustituiría a esa herramienta.

## `specs`

**Cabecera:** Specs

**Pregunta:** En la metodología, una spec describe qué se construye y sus criterios de aceptación (`AC-NN`), cada uno con un test. Tiene un ID y un estado (borrador → aprobada → implementada → sustituida). Tu repo tiene {N documentos en `rfcs/` con IDs `RFC-NNN`}. ¿Qué hacemos con ellos?

- **Mapearlas tal cual (Recomendado)**: se quedan donde están y con sus IDs, y se adaptan al formato cuando alguien las toca. Vista previa: `paths.specs = "rfcs" · [ids.RFC] pattern = 'RFC-\d{3}'`. Respuesta: `{"option": "mapear", "path": "rfcs", "kind": "RFC", "pattern": "RFC-\\d{3}"}`
- **Convertirlas ahora**: las reescribes al formato de spec en la rama de adopción; el PR será grande. Vista previa: `rfcs/012-auth.md → specs/features/SPEC-NNNN-auth.md`. Respuesta: `{"option": "convertir"}`
- **Archivarlas**: se mueven a `docs/archivo/` como histórico y las specs nuevas empiezan en `SPEC-0001`. Respuesta: `{"option": "archivar"}`

## `decisiones`

**Cabecera:** Decisiones

**Pregunta:** Un ADR registra por qué se tomó una decisión estructural, y la metodología no admite decisiones de ese tipo sin uno. Tu repo tiene {N decisiones en `docs/decisions/`}. ¿Qué hacemos con ellas?

- **Mapearlas tal cual (Recomendado)**: Respuesta: `{"option": "mapear", "path": "docs/decisions", "kind": "ADR", "pattern": "ADR-\\d{3}"}`
- **Convertirlas ahora**: Respuesta: `{"option": "convertir"}`
- **Archivarlas**: Respuesta: `{"option": "archivar"}`

Descripciones y vistas previas: las de `specs`, aplicadas a los ADR.

## `tests`

**Cabecera:** Tests

**Pregunta:** La metodología ejecuta los tests antes de cada integración y publicación: con tests en rojo no se integra. He encontrado {`pytest` y `make test` / ningún comando}. ¿Cuál es el comando de referencia?

- **`{candidato}`**: uno por candidato. Respuesta: `{"option": "comando", "command": "{candidato}"}`
- **Aún no hay tests**: `mth doctor` lo recordará en cada diagnóstico. Respuesta: `{"option": "ninguno"}`

## `revisores`

**Cabecera:** Revisores (selección múltiple, sin vista previa)

Se hace siempre: también ofrece los agentes del catálogo del plugin (SPEC-0012 de claude-methodology).

**Pregunta 1:** Antes de integrar, la metodología revisa cada rama con agentes de contexto limpio: solo ven el diff, las specs y los principios. Siempre va primero el `verificador` del plugin, que comprueba que la rama cumple su spec. En tu repo hay {`security-reviewer`, `api-reviewer`}. ¿Cuáles añadimos como revisores?

- Una opción por agente del repo, con su `description` como descripción. Si el repo no tiene agentes, omite esta pregunta.

**Pregunta 2 (catálogo):** El plugin trae agentes listos para instalar en el repo, adaptados a su configuración y con un guard que limita lo que pueden ejecutar. Te propongo el perfil `base`. ¿Cuáles instalamos?

- Una opción por agente del perfil `base`, **todas marcadas**: `revisor-seguridad`, `revisor-fallos`, `revisor-adr`, `revisor-diseno`, `revisor-parsimonia` (revisores) y `diagnosticador`, `explorador-specs` (trabajadores). Desmarca de antemano `diagnosticador` si no habrá `commands.test`, y cualquiera cuyo nombre ya use un agente del repo (sería una colisión: se resuelve después con `mth agents add --replace`).
- Menciona los opcionales (`ingeniero-rendimiento`, `analista-evals`, `lector-estado`, `respondedor-incidencias`) solo si el inventario muestra benchmarks, evals, bases SQLite de estado o un fork; si elige alguno, pide sus variables obligatorias (`bench`, `results`, `databases`).

Respuesta: `{"option": "agentes", "agents": ["security-reviewer"], "catalog": ["revisor-seguridad", "revisor-fallos"], "vars": {"lector-estado": {"databases": {"estado": "data/state.db"}}}}`. `agents` es la lista de agentes del repo (vacía si no elige ninguno); `catalog` y `vars` son opcionales. Después propón `[review.paths]` para los del repo que solo aplican a un área.

## `colision`

**Cabecera:** Colisión

**Pregunta:** El plugin incluye el agente `{verificador}`, y tu repo tiene otro con el mismo nombre que {resumen de su description}. Con el mismo nombre, el tuyo sustituye al del plugin sin aviso. ¿Qué hacemos?

- **Renombrar el tuyo (Recomendado)**: pasa a llamarse `{verificador-repo}` y se usan los dos. Respuesta: `{"option": "renombrar", "renames": {"{verificador}": "{verificador-repo}"}}`
- **Usar el tuyo en ese rol**: pierdes la comprobación del plugin. Respuesta: `{"option": "mantener"}`

## `instrucciones`

**Cabecera:** Instrucciones

Antes de preguntar, lee {CLAUDE.md / AGENTS.md}. Si nada contradice las reglas base, no hagas la pregunta y responde `{"option": "metodologia"}`.

**Pregunta:** El plugin añade sus reglas a CLAUDE.md. Tu {CLAUDE.md} dice «{cita}» y «{cita}», que chocan con la metodología. Si conviven, Claude recibe órdenes contradictorias. ¿Qué prevalece?

- **La metodología (Recomendado)**: retiras esas líneas en la rama de adopción. Respuesta: `{"option": "metodologia"}`
- **Lo del repo**: solo en lo que no es innegociable (historia compartida, specs, trazabilidad); queda en el ADR de adopción. Respuesta: `{"option": "repo", "exceptions": ["{cita}"]}`

## `autonomia`

**Cabecera:** Autonomía

**Pregunta:** Por defecto, Claude crea ramas, hace commits, integra y publica versiones sin preguntar. Todo pasa por gates deterministas (tests, revisión, CI) y nada reescribe historia, y Claude solo se detiene ante contradicciones, fallos repetidos o acciones irreversibles. ¿Cuánta autonomía le das en este repo?

- **Completa (Recomendado)**: el ciclo entero sin interrupciones; revisas los PR y las versiones cuando quieras. Vista previa: `spec → rama → código → revisión → PR → v1.4.0`. Respuesta: `{"option": "full"}`
- **Hasta el PR**: integrar y publicar te piden confirmación. Vista previa: `… → revisión → ⏸ ¿integrar? → ⏸ ¿publicar?`. Respuesta: `{"option": "until-pr"}`
- **Supervisada**: además, cada rama nueva, commit y push. Más lento, pero ves cada paso. Vista previa: `⏸ ¿rama? ⏸ ¿commit? … ⏸ ¿integrar?`. Respuesta: `{"option": "supervised"}`

## `idioma`

**Cabecera:** Idioma

**Pregunta:** La metodología escribe el código y los commits en inglés, y la documentación, las specs, el changelog y los PR en el idioma del repo. {Tus docs están en inglés / El repo aún no tiene docs}. ¿En qué idioma se escribe la documentación?

- **{Inglés / Español} (Recomendado: el detectado)**: plantillas y palabras clave (`Status: implemented`, `## Work plan`, `### Added`) en ese idioma. Respuesta: `{"option": "en"}` o `{"option": "es"}`
- **{El otro}**: Respuesta: `{"option": "es"}` o `{"option": "en"}`

## `ci`

**Cabecera:** CI

**Pregunta:** La metodología puede exigir la CI en verde para integrar (fail-safe: sin CI no se integra). Tu repo no tiene workflows. ¿Qué hacemos?

- **Sin CI por ahora (Recomendado)**: `mth doctor` avisará hasta que exista. Respuesta: `{"option": "sin-ci"}`
- **Crear un workflow básico**: escribes en la rama de adopción un workflow que ejecute `commands.test`. Respuesta: `{"option": "crear"}`

## `modelos`

**Cabecera:** Modelos

**Pregunta:** Claude delega tareas en subagentes y elige el modelo de cada una según su dificultad; si una falla, la reintenta un nivel más arriba. Los niveles equilibran coste y calidad. ¿Qué escalera usamos?

- **Equilibrado (Recomendado)**: Vista previa: `haiku → sonnet → opus · revisión: sonnet`. Respuesta: `{"option": "equilibrado"}`
- **Calidad**: Vista previa: `sonnet → opus · revisión: opus`. Respuesta: `{"option": "calidad"}`
- **Ahorro**: Vista previa: `haiku → sonnet · revisión: sonnet`. Respuesta: `{"option": "ahorro"}`
