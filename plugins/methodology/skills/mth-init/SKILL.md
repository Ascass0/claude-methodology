---
name: mth-init
description: Adopta claude-methodology en un repositorio o diagnostica su adopción. Úsala cuando el contexto de sesión diga que falta .claude/methodology.toml, cuando el usuario pida preparar o configurar un repo con la metodología, o cuando algo de la metodología falle (hook commit-msg, configuración inválida, gh sin autenticar).
---

# Adoptar la metodología

`mth` es el comando del contexto de sesión (`$MTH`).

## Repo nuevo

1. Árbol limpio y remoto con `main`.
2. `mth init --marketplace-repo <owner>/claude-methodology --github`
   - Crea `development` si no existe, abre `chore/adopt-methodology` y hace commit de: `.claude/methodology.toml`, `docs/`, `specs/features/`, `specs/adr/`, `changes/`, `CHANGELOG.md`, el bloque de `CLAUDE.md` y la activación del plugin en `.claude/settings.json`.
   - Instala el hook `commit-msg`.
   - `--github` aplica en GitHub: solo merge commits y ruleset de `main`/`development` (PR obligatorio, sin borrado ni force-push). Requiere permisos de admin; si falla, avisa y continúa.
3. Ajusta `.claude/methodology.toml` al repo, en un commit `chore(methodology)`:
   - `commands.test` (y `precommit` si hay lint rápido).
   - `[ids]` si el repo ya tiene su propio esquema (por ejemplo `F-\d{3}` definido en `docs/02-*.md`).
   - `review.agents`: los agentes revisores existentes en `.claude/agents/`, en orden de precedencia.
   - `[roles]` y `[branches.extra]` si aplican.
   - `ci.required = true` en cuanto el repo tenga CI.
4. `mth doctor` sin ✗.
5. `mth trace`: corrige los hallazgos del contenido previo (enlaces fuera del repo, IDs duplicados) o exclúyelos de forma explícita en `trace.exclude` con su motivo en el commit.
6. Integra con la skill `mth-integrate` (`--title "chore(methodology): adopt claude-methodology"`).

## Diagnóstico

`mth doctor` lista cada comprobación con ✓, ✗ (bloquea) o ⚠ (aviso). Corrige los ✗ en una rama `chore/`.
