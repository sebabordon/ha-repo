# Gastos Tarjetas — Claude project instructions

## Version bumping & changelog (MANDATORY)

Every commit that changes any code or behaviour MUST:

1. **Bump the version** in ALL three places (keep them in sync):
   - `config.yaml` → `version: "X.Y.Z"`
   - `rootfs/app/config.py` → `APP_VERSION = "X.Y.Z"`

2. **Prepend a new entry** to `CHANGELOG.md` with the same version number.
   - Use the existing Spanish prose style.
   - One bullet per logical change; be specific (what changed, why, where).
   - Place the new entry ABOVE the previous top entry.

Never commit without doing both. If a PR/push contains more than one logical
change, group them under a single version entry — don't split into micro-bumps
unless the changes are deployed separately.

3. **Push to GitHub** immediately after committing (`git push`).
   Every session that produces a commit must end with a push — GitHub must
   never lag behind the local repo.

## Security

- NEVER commit anything inside `samples/` — those files contain real personal
  financial PDFs. The directory is `.gitignore`d; keep it that way.

## Code conventions

- Sign convention: `monto > 0` = egreso (money out), `monto < 0` = ingreso.
  This applies to ALL sources after the `normalize_signs_v1` migration.
- CC parsers (amex, bbva_mc, bbva_visa, galicia_mc) return positive = expense
  already; non-CC parsers need the sign flipped in `upload.py`.
- `_CC_FUENTES` in `db.py` is the authoritative list of credit-card sources.
- Parser instance attributes set after `parse()` (`fecha_vencimiento`,
  `stmt_total_ars`, `stmt_total_usd`, `saldo_final`) are read in `upload.py`
  via `getattr(PARSERS[fuente], "attr", None)`.
