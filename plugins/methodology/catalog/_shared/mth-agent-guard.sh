#!/bin/sh
# claude-methodology · guard por agente (SPEC-0012, ADR-0008). `mth agents add` lo instala,
# versionado, en .claude/hooks/mth-agent-guard. Lo invoca la entrada PreToolUse de
# .claude/settings.json en cada llamada a Bash, Write o Edit de la sesión.
#
# - Sesión principal (el payload no trae agent_id ni agent_type): sale con 0 sin lanzar Python.
# - Subagente: pasa el payload a `mth agent-guard`, que decide según agent_type.
#
# Falla CERRADO con los subagentes: sin repositorio, sin lanzador o con cualquier código de
# salida distinto de 0 del guard, bloquea (exit 2). Es lo contrario del guard global, que falla
# abierto por diseño: un agente "de solo lectura" que escribe porque el guard se rompió es peor
# que un agente parado.
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
dir="${CLAUDE_PROJECT_DIR:-.}"
common=$(git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || {
  echo "[mth-agent-guard] No es un repositorio git: se bloquea la herramienta." >&2; exit 2; }
python=$(sed -n 1p "$common/mth/launcher" 2>/dev/null)
script=$(sed -n 2p "$common/mth/launcher" 2>/dev/null)
if [ -z "$python" ] || [ ! -x "$python" ] || [ -z "$script" ] || [ ! -f "$script" ]; then
  echo "[mth-agent-guard] claude-methodology no encontrado: abre una sesión nueva de Claude Code." >&2
  exit 2
fi
printf '%s' "$input" | "$python" "$script" agent-guard
rc=$?
[ "$rc" -eq 0 ] && exit 0
[ "$rc" -eq 2 ] || echo "[mth-agent-guard] El guard terminó con código $rc: se bloquea por seguridad." >&2
exit 2
