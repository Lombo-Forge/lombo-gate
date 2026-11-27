---
name: install-into-my-stack
description: Help a user install LomboGate next to their own Seerr and verify it with doctor. Use when someone asks to set it up, install it, or add it to their compose file or server.
---

# Install LomboGate into the user's stack

Ask, one question at a time, and use their answers (never assume a layout):

1. **How do you run Seerr and Sonarr?** For compose, add the service from `compose.example.yaml` and join their network. Otherwise use the machine's address and ports, only in their own `.env`.
2. **API keys:** Seerr and Sonarr, Settings > General. Seerr's key has full control; keep it private.
3. **Limits:** how many seasons and how many GB may be approved without them? Which Sonarr quality do they usually download?
4. **Optional alerts:** a Discord, Slack or similar webhook, or leave it empty.
5. **Write `.env`** from `.env.example`. Keep `LOMBO_GATE_DRY_RUN=true`. Never print keys back.
6. **Start and check:** `docker compose up -d --build`, then `lombo-gate doctor` inside it.
7. **Auto-approve:** have them turn it off in Seerr for the users `doctor` names, and for new users. Without this nothing is gated.
8. **Show `lombo-gate plan`**, then set `LOMBO_GATE_DRY_RUN=false` only when they say so.

If `doctor` fails, read the `troubleshoot` skill.
