#!/bin/sh
# claude-methodology · guard por agente (SPEC-0012, ADR-0008). `mth agents add` lo instala,
# versionado, en .claude/hooks/mth-agent-guard. Lo invoca la entrada PreToolUse de
# .claude/settings.json en cada llamada a Bash, Write o Edit de la sesión.
#
# - Sesión principal (el payload no trae agent_id ni agent_type): sale con 0 sin lanzar Python.
# - Subagente: pasa el payload a `mth agent-guard`, que decide según agent_type.
#
# Falla CERRADO: sin repositorio, con un guard que no termina a tiempo o con cualquier código
# de salida distinto de 0, bloquea (exit 2). Sin lanzador (plugin ausente o anterior a 0.8.0)
# bloquea a los agentes del catálogo y a los que no puede identificar; los demás siguen. Es lo
# contrario del guard global, que falla abierto por diseño: un agente "de solo lectura" que
# escribe porque el guard se rompió es peor que un agente parado.
#
# `mth session` escribe en <git-common-dir>/mth/launcher el intérprete de Python (>= 3.11) y la
# ruta de mth.py vigentes, igual que reescribe el hook commit-msg, porque la ruta del plugin
# cambia con cada versión. Se usa el git-common-dir para que funcione también desde un worktree
# (isolation: worktree). Invocar el intérprete directamente evita buscarlo en cada llamada.
input=$(cat)
case "$input" in
  *'"agent_id"'*|*'"agent_type"'*) ;;
  *) exit 0 ;;
esac
# Límites de tiempo por debajo del timeout de la entrada del hook (30 s): si vencen, se bloquea.
# timeout(1) o, donde no existe (macOS sin coreutils), perl; el guard tiene además su propio límite.
bounded() {
  secs=$1; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$secs" "$@"
  else perl -e 'alarm shift; exec @ARGV or exit 127' "$secs" "$@"
  fi
}
if ! command -v timeout >/dev/null 2>&1 && ! command -v perl >/dev/null 2>&1; then
  echo "[mth-agent-guard] Faltan timeout y perl: sin un límite de tiempo no se garantiza el bloqueo. Instala coreutils o perl." >&2
  exit 2
fi
# Campos del payload para correlacionar el registro (sin intérprete): el valor no lleva comillas ni barras.
# Registro de los bloqueos que decide el propio shim (el guard no llegó a ejecutarse o no pudo registrarlo).
# Rota a .1 por encima de 1 MiB, como el guard. Sin repositorio ni límite de tiempo no hay dónde escribir.
log_block() {  # $1 categoría, $2 motivo (texto fijo)
  f="$common/mth/agent-guard.jsonl"
  ( umask 077; mkdir -p "$common/mth" || exit 1
    if [ -f "$f" ] && [ "$(wc -c < "$f")" -gt 1048576 ]; then mv -f "$f" "$f.1"; fi
    printf '{"ts": "%s", "event": "agent_guard.decision", "cmd": "shim", "agent": "%s", "session": "%s", "tool": "%s", "result": "deny", "category": "%s", "reason": "%s"}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$(field agent_type)" "$(field session_id)" "$(field tool_name)" "$1" "$2" >> "$f" ) 2>/dev/null
}
field() { printf '%s' "$input" | sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"\\\\]*\)\".*/\1/p" | head -n 1; }
dir="${CLAUDE_PROJECT_DIR:-.}"
common=$(bounded 5 git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
rc=$?
if [ "$rc" -ne 0 ]; then
  case "$rc" in
    124|142) echo "[mth-agent-guard] git no respondió en 5 s: se bloquea la herramienta." >&2 ;;
    *) echo "[mth-agent-guard] No es un repositorio git: se bloquea la herramienta." >&2 ;;
  esac
  exit 2
fi
guard_timeout="${MTH_AGENT_GUARD_TIMEOUT:-20}"   # acotado: por encima de 25 s vencería antes el hook (30 s), que no bloquea
case "$guard_timeout" in ''|*[!0-9]*) guard_timeout=20 ;; esac
[ "$guard_timeout" -le 25 ] || guard_timeout=20
python=$(sed -n 1p "$common/mth/launcher" 2>/dev/null)
script=$(sed -n 2p "$common/mth/launcher" 2>/dev/null)
if [ -z "$python" ] || [ ! -x "$python" ] || [ -z "$script" ] || [ ! -f "$script" ]; then
  agent=$(field agent_type)
  # agent_type repetido: un dato anidado (argumentos de una herramienta) podría suplantar al agente real.
  [ "$(printf '%s' "$input" | grep -o '"agent_type"' | wc -l)" -le 1 ] || agent=""
  case "$agent" in
    "") ;;                                  # sin identificar: se bloquea
    *[!a-z0-9-]*|-*) exit 0 ;;              # no es un nombre del catálogo (methodology:verificador, Explore)
    *) if [ ! -f "$dir/.claude/mth/agents/$agent.guard.toml" ] &&
          ! grep -q '<!-- mth:template ' "$dir/.claude/agents/$agent.md" 2>/dev/null; then
         exit 0                              # agente propio del repo
       fi ;;
  esac
  echo "[mth-agent-guard] claude-methodology no encontrado: abre una sesión nueva de Claude Code con el plugin >= 0.8.0." >&2
  log_block launcher-missing "no hay lanzador registrado"
  exit 2
fi
printf '%s' "$input" | bounded "$guard_timeout" "$python" "$script" agent-guard
rc=$?
[ "$rc" -eq 0 ] && exit 0
[ "$rc" -eq 2 ] && exit 2
echo "[mth-agent-guard] El guard terminó con código $rc: se bloquea por seguridad." >&2
# El guard no pudo registrarlo él mismo: timeout(1) = 124, SIGALRM de perl = 142; cualquier otro código es un fallo.
case "$rc" in 124|142) category=timeout ;; *) category=crash ;; esac
log_block "$category" "el guard terminó con código $rc"
exit 2
