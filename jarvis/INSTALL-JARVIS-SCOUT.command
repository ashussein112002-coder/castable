#!/bin/bash
# INSTALL-JARVIS-SCOUT.command — give Jarvis the /scout command and let the loop redeploy the bot.
#
# What it does (idempotent, one commit, no push, no history rewrite):
#   1. copies jarvis/scout_door.py -> ~/jarvis-agent/src/jarvis/tools/scout_door.py
#   2. registers Command(("scout",), "_cmd_scout", ...) in src/jarvis/bridge/commands.py (after /marcador)
#   3. appends the _cmd_scout handler to src/jarvis/bridge/bot.py
#   4. import check with the bot's own venv, then `git commit`
#   5. writes ~/jarvis-vault/70_loop/deploy/jarvis-next.txt "<branch> <sha>" -> the loop's watcher runs
#      DESPLEGAR-JARVIS.command on its next tick (<= 5 min) and restarts the bot (a Telegram card confirms)
# Refuses to touch a dirty tree. DRY=1 shows the edits without writing.
set -u
JA="${JARVIS_AGENT:-$HOME/jarvis-agent}"; V="${JARVIS_VAULT:-$HOME/jarvis-vault}"
HERE="$(cd "$(dirname "$0")" && pwd)"; SRC="$HERE/scout_door.py"
DRY="${DRY:-0}"
say() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { say "STOP: $*"; [ "${SCOUT_NO_TTY:-0}" = 1 ] || read -r -p "Enter to close" _; exit 1; }
g() { git --no-optional-locks -C "$JA" "$@"; }

[ -f "$SRC" ] || die "missing $SRC"
[ -d "$JA/src/jarvis/bridge" ] || die "jarvis-agent not found at $JA"
DIRTY=$(g status --porcelain -uno 2>/dev/null | cut -c4- | grep -v '^\.claude/')
[ -z "$DIRTY" ] || die "jarvis-agent has uncommitted tracked changes: $(echo $DIRTY)"
BR=$(g symbolic-ref --short -q HEAD) || die "detached HEAD in $JA"
say "jarvis-agent on $BR $(g rev-parse --short HEAD)"

# 1. the door
if [ "$DRY" = 1 ]; then say "DRY would copy $SRC -> $JA/src/jarvis/tools/scout_door.py"
else cp "$SRC" "$JA/src/jarvis/tools/scout_door.py" && say "copied scout_door.py"; fi

# 2 + 3. registry + handler (python does the in-place edits, idempotently)
DRY="$DRY" JA="$JA" /usr/bin/python3 - <<'PY' || exit 1
import os, re, sys
ja = os.environ["JA"]; dry = os.environ.get("DRY") == "1"
cmds = os.path.join(ja, "src/jarvis/bridge/commands.py")
bot = os.path.join(ja, "src/jarvis/bridge/bot.py")
s = open(cmds, encoding="utf-8").read()
if '"scout"' not in s:
    m = re.search(r'^(\s*)Command\(\("marcador".*?\),\s*"_cmd_marcador",(.*?)\),\s*$', s, re.M)
    if not m:
        print("STOP: could not find the /marcador Command line to model /scout on"); sys.exit(1)
    indent, tail = m.group(1), m.group(2)
    line = f'{indent}Command(("scout", "casting"), "_cmd_scout",{tail}),\n'
    s = s[:m.end()] + "\n" + line.rstrip("\n") + s[m.end():]
    print("registry: adding", line.strip())
    if not dry:
        open(cmds, "w", encoding="utf-8").write(s)
else:
    print("registry: /scout already present")
b = open(bot, encoding="utf-8").read()
if "async def _cmd_scout" not in b:
    handler = '''

async def _cmd_scout(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/scout <brief> — Scout by VYRAL: brief -> vetted creator shortlist with video evidence.
    The whole door lives in tools/scout_door.py (HTTP to the local Scout app, nothing else)."""
    if not _is_allowed(update):
        log.warning("Ignorado /scout de chat NO autorizado: %s", update.effective_chat.id)
        return
    from jarvis.tools import scout_door
    await scout_door.cmd_scout(update, ctx)
'''
    print("bot: appending _cmd_scout handler")
    if not dry:
        open(bot, "a", encoding="utf-8").write(handler)
else:
    print("bot: _cmd_scout already present")
PY

[ "$DRY" = 1 ] && { say "DRY run complete"; exit 0; }

# 4. import check with the bot's venv, then commit
( cd "$JA" && PYTHONPATH=src ./.venv/bin/python -c "import jarvis.bridge.commands, jarvis.tools.scout_door; import jarvis.bridge.bot" ) \
  || { say "import check FAILED — reverting"; g checkout -- src/jarvis/bridge/commands.py src/jarvis/bridge/bot.py; rm -f "$JA/src/jarvis/tools/scout_door.py"; die "not committed"; }
g add src/jarvis/tools/scout_door.py src/jarvis/bridge/commands.py src/jarvis/bridge/bot.py
if g diff --cached --quiet; then say "nothing to commit (already installed)"; SHA=$(g rev-parse HEAD)
else
  g commit -q -m "jarvis: /scout — Scout by VYRAL door (creator casting with video evidence, Oriane x Replit hackathon)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" || die "commit failed"
  SHA=$(g rev-parse HEAD); say "committed $BR ${SHA:0:7}"
fi

# 5. hand the restart to the loop's watcher
mkdir -p "$V/70_loop/deploy"
printf '%s %s\n' "$BR" "$SHA" > "$V/70_loop/deploy/jarvis-next.txt"
say "wrote 70_loop/deploy/jarvis-next.txt -> the loop restarts Jarvis on its next tick (<= 5 min); watch Telegram for the card"
say "manual alternative right now: bash $V/DESPLEGAR-JARVIS.command"
[ "${SCOUT_NO_TTY:-0}" = 1 ] || read -r -p "Enter to close" _
