# Anteny - Pokyny pro vývoj a práci s KiCad

## Zásady práce v projektu
- **Verzování a Git**: Commity piš dle **Conventional Commits v angličtině** (např. `feat:`, `fix:`, `docs:`, `chore:`). Složky `kicad/` a `export/` jsou v `.gitignore`.
- **Docker prostředí**: Pro operace s KiCad (exporty, validace, Gerber podklady) používej Docker profil z `docker-compose.yml`:
  `docker compose --profile kicad-export run --rm kicad`

## Tvorba součástek a knihoven v KiCad
- Při vytváření nebo úpravě symbolů a pouzder v KiCad postupuj podle skillu `kicad-component` v `.agents/skills/kicad-component/SKILL.md`.
- Dbej na rozdílné souřadné systémy: schéma má osu Y kladnou nahoru, DPS má osu Y kladnou dolů.
