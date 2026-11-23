#!/bin/sh
# claude-methodology · guard por agente (referencia). `mth agents add` lo instala, versionado, en
# .claude/hooks/mth-agent-guard. Lo invoca el hook PreToolUse del frontmatter de cada agente del
# catálogo: `sh "$CLAUDE_PROJECT_DIR/.claude/hooks/mth-agent-guard" <agente>`.
#
# Falla CERRADO: si no encuentra mth, el agente no ejecuta la herramienta (exit 2). Es lo contrario
# del guard global, que falla abierto por diseño: este solo afecta a un subagente acotado, y un
# agente "de solo lectura" que escribe cuando el guard se rompe es peor que un agente parado.
#
# El lanzador vigente lo escribe `mth session` en <git-common-dir>/mth/launcher, igual que reescribe
# el hook commit-msg, porque la ruta del plugin cambia con cada versión. Se usa el git-common-dir
# para que también funcione desde un worktree (agentes con isolation: worktree).
agent="$1"
[ -n "$agent" ] || { echo "[mth-agent-guard] Falta el nombre del agente." >&2; exit 2; }
common=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --git-common-dir 2>/dev/null) || {
  echo "[mth-agent-guard] No es un repositorio git: se bloquea la herramienta." >&2; exit 2; }
case "$common" in /*) ;; *) common="${CLAUDE_PROJECT_DIR:-.}/$common" ;; esac
launcher=$(cat "$common/mth/launcher" 2>/dev/null)
[ -n "$launcher" ] && [ -f "$launcher" ] || {
  echo "[mth-agent-guard] claude-methodology no encontrado. Abre una sesión nueva de Claude Code." >&2; exit 2; }
exec sh "$launcher" agent-guard "$agent"
