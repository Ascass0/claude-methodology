# ADR-0020 · Gate de secretos en el historial

- Estado: aceptado
- Fecha: 2026-11-26
- Categoría: security
- Formato: compacto

## Contexto

- Una credencial subida al historial compartido está comprometida desde ese momento: borrarla del código no la invalida y la metodología prohíbe reescribir historia compartida (§ reglas base).
- Prevenir es más barato que diagnosticar: la comprobación debe correr antes de que el secreto llegue a `development`, sin depender de que alguien se acuerde.
- Un repo adoptado puede tener ya secretos en su historial: bloquear por ellos el primer día lo deja sin poder integrar y la gente apaga el gate.
- Activar un gate que exige una herramienta externa sin preguntar rompe repos que no la tienen.
- Lo comprobable se automatiza (§0); un escáner de secretos es determinista y casi sin falsos positivos.

## Decisión

1. `mth integrate` DEBE escanear los commits de la rama con `gitleaks` antes de subirla cuando `secrets.mode = "block"`. Un hallazgo no aceptado bloquea y no se sube nada. [script: `mthlib/secretgate.py`, `mthlib/flow.py`]
2. `secrets.mode` admite `""` (sin decidir, valor por defecto), `"off"` y `"block"`. Sin decidir es una brecha de clase `decision` en `mth update`; la elección se registra en el ADR de adopción o de actualización. Nunca se activa en silencio.
3. `mth secrets` escanea la rama sobre su destino; `--history` escanea todo el historial. Con la herramienta ausente o fallando devuelve error: falla cerrado, no se da por limpio.
4. Los hallazgos se imprimen con regla, fichero, línea y commit corto; nunca el valor. El informe temporal de la herramienta se pide con `--redact` y se borra siempre.
5. Los hallazgos ya existentes se aceptan de forma explícita con `mth secrets --history --accept`, que escribe `secrets.baseline` (informe redactado). Solo los hallazgos fuera de la línea base bloquean. Aceptar no limpia: el comando avisa de que el secreto debe rotarse.
6. La remediación de un secreto filtrado es rotarlo; ningún comando de `mth` reescribe historia.
7. `mth doctor` marca ✗ si `mode = "block"` y falta `gitleaks`, y ⚠ si el modo está sin decidir o en `off`.

## Rechazado

- Activado por defecto: rompe los repos sin la herramienta y esconde la decisión.
- trufflehog: licencia AGPL y verificación contra servicios reales; gitleaks es MIT y local.
- Escanear solo en la CI: no cubre a quien no use `mth` ni evita subir el secreto; la CI sigue siendo la red de respaldo.
- Hook de precommit en esta iteración: el hook local no se puede imponer y exige instalarlo en cada clon; queda para una spec posterior.
- Limpiar el historial con `filter-repo`: reescribe historia compartida y no invalida el secreto.
- Escáner propio con expresiones regulares: reinventa una herramienta madura y se queda atrás.

## Consecuencias

- **+** Un secreto nuevo no llega a `development` por el flujo de `mth`. La adopción con legado no se bloquea.
- **+** Aceptar un hallazgo viejo es explícito y queda en el repo.
- **−** Dependencia externa opcional (`gitleaks`) y una sección de configuración más.
- **riesgo** Aceptar un hallazgo sin rotarlo → el comando lo avisa y `revisor-seguridad` mira la línea base en el diff.
- **riesgo** El gate se apaga con `mode = "off"` → `mth doctor` lo marca y el cambio queda en el diff.
- **riesgo** Un escáner no detecta toda contraseña (p. ej. una inventada en un fichero) → barrera, no garantía.

## Impone

- [script] `mthlib/secretgate.py` (escaneo, informe y línea base), `mthlib/flow.py` (gate de `mth integrate`), `mthlib/config.py` (`[secrets]`), `mthlib/update.py` (brecha `secretos`), `mthlib/setup.py` (`mth doctor`).
- [criterio] `revisor-seguridad` mira los cambios de `secrets.baseline` y de `secrets.mode`.
