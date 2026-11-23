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
  elif command -v perl >/dev/null 2>&1; then perl -e 'alarm shift; exec @ARGV or exit 127' "$secs" "$@"
  else "$@"
  fi
}
dir="${CLAUDE_PROJECT_DIR:-.}"
common=$(bounded 5 git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || {
  echo "[mth-agent-guard] No es un repositorio git: se bloquea la herramienta." >&2; exit 2; }
python=$(sed -n 1p "$common/mth/launcher" 2>/dev/null)
script=$(sed -n 2p "$common/mth/launcher" 2>/dev/null)
if [ -z "$python" ] || [ ! -x "$python" ] || [ -z "$script" ] || [ ! -f "$script" ]; then
  agent=$(printf '%s' "$input" | sed -n 's/.*"agent_type"[[:space:]]*:[[:space:]]*"\([^"\\]*\)".*/\1/p' | head -n 1)
  case "$agent" in
    "") ;;                                  # sin identificar: se bloquea
    *[!a-z0-9-]*|-*) exit 0 ;;              # no es un nombre del catálogo (methodology:verificador, Explore)
    *) if [ ! -f "$dir/.claude/mth/agents/$agent.guard.toml" ] &&
          ! grep -q '^<!-- mth:template ' "$dir/.claude/agents/$agent.md" 2>/dev/null; then
         exit 0                              # agente propio del repo
       fi ;;
  esac
  echo "[mth-agent-guard] claude-methodology no encontrado: abre una sesión nueva de Claude Code con el plugin >= 0.8.0." >&2
  exit 2
fi
printf '%s' "$input" | bounded 20 "$python" "$script" agent-guard
rc=$?
[ "$rc" -eq 0 ] && exit 0
[ "$rc" -eq 2 ] && exit 2
echo "[mth-agent-guard] El guard terminó con código $rc: se bloquea por seguridad." >&2
case "$rc" in 124|142)  # timeout(1) / SIGALRM de perl: el guard no pudo registrarlo él mismo
  ( umask 077; mkdir -p "$common/mth" &&
    printf '{"event": "agent_guard.decision", "cmd": "shim", "result": "deny", "category": "timeout", "reason": "el guard no terminó a tiempo (código %s)"}\n' "$rc" \
      >> "$common/mth/agent-guard.jsonl" ) 2>/dev/null ;;
esac
exit 2
