# ADR-0004 · Autonomía configurable por repositorio

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

PRINCIPLES §11 establece la autonomía completa: Claude crea ramas, hace commits, integra y publica sin pedir permiso, y la supervisión que necesite un repo se añade con un hook propio de ese repo. En la práctica, casi ningún repo escribe ese hook, y la adopción guiada ([SPEC-0004](../../features/SPEC-0004-adopcion-guiada.md)) tiene que ofrecer niveles intermedios a equipos que no están dispuestos a la autonomía completa desde el primer día.

Fuerzas en juego:

- **La autonomía se apoya en gates deterministas.** Pedir confirmación no sustituye a los gates; se añade a ellos.
- **Claude Code ya sabe pedir confirmación.** Un hook `PreToolUse` puede responder `ask`, y Claude Code muestra la petición a la persona. En una sesión no interactiva, `ask` equivale a denegar.
- **El guard ya inspecciona cada comando Bash** para bloquear lo que se salta el flujo.

## Decisión

1. Tres niveles en `[autonomy] level`: `full` (por defecto, como hasta ahora), `until-pr` (se confirma integrar y publicar) y `supervised` (además, cada commit, cada rama nueva y cada push).
2. Lo aplica el guard existente con la decisión `ask` de Claude Code, no instrucciones en el contexto: una instrucción se puede olvidar; un hook no.
3. Si el guard no puede leer la configuración, pide confirmación como en `supervised` (fail-safe), en vez de dejar pasar sin confirmar. Sigue dejando pasar sin bloquear (fail-open) los comandos que no reconoce, como hasta ahora.
4. PRINCIPLES §11 describe los tres niveles. El resto de reglas de autonomía (cuándo detenerse, gates obligatorios) no cambia.

## Alternativas consideradas

- **Solo instrucciones en las reglas de sesión** ("pregunta antes de integrar"): no es verificable y se pierde al compactar el contexto.
- **Un hook de ejemplo para que cada repo lo copie:** cada repo acabaría con una variante distinta, y la adopción guiada no podría configurarlo.
- **Permisos de Claude Code (`permissions.ask`) en `.claude/settings.json`:** casan por prefijo de comando y no reconocen las distintas formas de invocar `mth` (`$MTH`, la ruta completa, `python mth.py`).

## Consecuencias

- **Positivas:** un equipo puede adoptar con supervisión y relajarla cambiando una clave. La adopción guiada lo pregunta.
- **Negativas:** en `supervised`, la sesión se interrumpe a menudo. Es el precio que elige quien lo configura.
- **Riesgo aceptado:** el guard reconoce invocaciones de `mth` por su forma. Una invocación muy indirecta (un script propio que llame a `mth`) no pedirá confirmación. El guard es una barrera para el agente, no una frontera de seguridad: las reglas de GitHub siguen protegiendo las ramas compartidas.
