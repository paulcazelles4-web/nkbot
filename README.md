# nkbot

## Railway
```
TOKEN=
PREFIX=s!
```

## Code gate (anyone with code)
- `s!help` public
- `s!help <CODE>` nuke menu
- `s!nuke` without code = unknown
- `s!nuke <CODE>` = nuke

No owner restriction. No promo spam.

Channel `#code` in main server for rotating code.

## Fix (2026-11-12)
- Removed fragile hex/zlib multi-file loader (`p0.txt`…`p34.txt`).
- Single-file `bot.py`, clearer boot logs, safer state dir.
- Still requires privileged intents: **Server Members Intent** + **Message Content Intent** in Discord Developer Portal.
