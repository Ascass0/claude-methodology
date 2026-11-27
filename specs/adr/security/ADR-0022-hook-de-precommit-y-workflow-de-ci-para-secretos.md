# ADR-0022 · Hook de precommit y workflow de CI para secretos

- Estado: aceptado
- Fecha: 2026-11-26
- Categoría: security
- Formato: compacto

## Contexto

- [ADR-0020](ADR-0020-gate-de-secretos-en-el-historial.md) escanea al integrar y dejó el hook de precommit «para una spec posterior» y la CI como red de respaldo sin plantilla.
- Un secreto ya está en el historial local cuando `mth integrate` lo detecta; un hook lo frena antes del commit.
- Un hook local no se puede imponer a cada clon ni evita `--no-verify`: la barrera que cuenta es la CI, que corre aunque el autor no use `mth`.
- Una herramienta externa no se activa sin preguntar (ADR-0020): ambas piezas son decisiones de la persona.

## Decisión

1. Con `secrets.hook = "on"` se instala un hook `pre-commit` que ejecuta `mth secrets --staged`, que escanea solo lo preparado con `gitleaks`. Falla cerrado: sin `gitleaks`, con un fallo de la herramienta o al agotar el tiempo, el commit se rechaza. Es la misma regla que el gate de ADR-0020. [script: `mthlib/secretgate.py`, `mthlib/setup.py`]
2. `hooks.pre_commit` (`own`, `replace`, `chain`) gobierna la convivencia con un hook ajeno igual que `hooks.commit_msg` ([SPEC-0006](../../features/SPEC-0006-hooks-commit-msg-encadenados.md)); no se toca nada si el directorio de hooks está versionado. [script]
3. Con `secrets.ci = "on"`, `forge = github` y `ci.required = true`, `mth` escribe `.github/workflows/secrets.yml` desde una plantilla del plugin: escanea el rango del PR y los push a `main` y `development`, descarga el binario de `gitleaks` con versión y SHA-256 fijados y fija por SHA las acciones que usa. No usa acciones de terceros para escanear. [script: plantilla y `mthlib/secretci.py`]
4. El fichero lleva una marca en su primera línea: sin ella es ajeno y `mth` no lo sobrescribe. `secrets.baseline` solo se sustituye en la plantilla si contiene letras, cifras, `.`, `_`, `-` y `/`, no empieza por `-` y no tiene `..` (el valor viene del repo y acaba dentro de un script de CI). [script]
5. `secrets.hook` y `secrets.ci` nacen sin decidir (`""`). `mth-init` pregunta `secretos` (`bloquear`, `integrar`, `ninguno`) y `mth update` lista una brecha de decisión por pieza mientras falten; nunca se activan en silencio. [script: `mthlib/update.py`, `mthlib/survey.py`]
6. Decididas, `mth update` corrige el hook y el workflow que falten o estén desactualizados (brecha automática) y `mth doctor` informa de su estado y de la versión de `gitleaks` (mínima 8.19.0). [script]
7. La protección de rama debe exigir la comprobación del workflow: una rama puede editarlo o borrarlo en su propio PR. `revisor-adr` ya vigila `.github/workflows/**` por `review.paths`. [criterio]

## Rechazado

- Hook que deja pasar sin `gitleaks`: contradice ADR-0020 («no se da por limpio») y «denegar, no degradar».
- `gitleaks/gitleaks-action`: dependencia de terceros con condiciones de licencia propias; el binario fijado y verificado no las tiene.
- Paso dentro del workflow de CI del repo: acopla el gate a un fichero que cada repo organiza a su manera; un fichero propio es idempotente y detectable.
- Escribir el workflow con un modelo: es un fichero determinista; lo escribe `mth` desde la plantilla.
- Activarlos por defecto: rompe repos sin la herramienta y esconde la decisión.
- Escanear también ficheros sin seguimiento: más lento, con falsos positivos, y lo que no se prepara no entra en el commit.
- Otras forjas en esta iteración: `mth` solo genera CI de GitHub (ADR-0012).

## Consecuencias

- **+** El secreto se frena antes del commit para quien activa el hook y en cada PR para todos.
- **+** La CI no depende de acciones de terceros ni de licencia.
- **−** Otro fichero que mantener (plantilla con versión y suma fijadas: subir la versión de `gitleaks` es un cambio del plugin) y tres claves de configuración más.
- **riesgo** `--no-verify` salta el hook → la CI y `mth integrate` siguen escaneando.
- **riesgo** Una rama hostil desactiva el workflow → protección de rama obligatoria y revisión de `.github/workflows/**`.
- **riesgo** En un PR, la línea base se lee del árbol del propio PR: quien lo abre puede ampliarla para aceptar su secreto → un cambio en `secrets.baseline` exige revisión humana (`revisor-seguridad` lo vigila en el diff, ADR-0020).
- **riesgo** `gitleaks` solo recibe parches de seguridad (el autor traslada el desarrollo a otro proyecto) → la plantilla fija una versión; cambiar de escáner exigiría un ADR nuevo.

## Impone

- [script] `mthlib/secretgate.py` (`--staged`), `mthlib/secretci.py` (workflow), `mthlib/setup.py` (hook `pre-commit`, workflow, `mth doctor`), `mthlib/config.py` (`secrets.hook`, `secrets.ci`, `hooks.pre_commit`), `mthlib/update.py` (brechas), `mthlib/survey.py` (pregunta `secretos`), plantilla `templates/workflows/secrets.yml`.
- [criterio] `revisor-adr` mira los cambios de `.github/workflows/**`.
