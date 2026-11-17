---
name: kicad-component
description: >-
  Postup tvorby schématických symbolů (.kicad_sym) a pouzder (.kicad_mod) pro KiCad 10
  pomocí kružnic a úseček a jejich validace přes Docker KiCad CLI.
---

# Tvorba KiCad 10 součástek (Symboly a Pouzdra)

Použij tento postup při vytváření grafických prvků, log nebo součástek pro KiCad v tomto projektu.

## 1. Pravidla geometrie a souřadnic
- **Pouze kružnice a čáry**:
  - Footprint DPS: `fp_arc` (3 body: start, mid, end) a `fp_line` (start, end) na vrstvě `F.SilkS`.
  - Schéma: `arc` (3 body: start, mid, end) a `polyline` (pts).
- **Orientace osy Y**:
  - **DPS (`.kicad_mod`)**: Osa +Y směřuje **dolů** (běžné grafické souřadnice).
  - **Schéma (`.kicad_sym`)**: Osa +Y směřuje **nahoru** (souřadnici Y je nutné negovat: `y_sym = -y_cad`).
- **Centrování**: Umísti střed tvaru na `(0, 0)` pro snadné vkládání a rotaci.
- **Barva pro schéma**: Pro černou barvu nastav explicitně `(stroke (width ...) (type default) (color 0 0 0 1))`.

## 2. Syntaxe S-výrazů (KiCad 10)

### Symbol v `.kicad_sym`
```lisp
(kicad_symbol_lib
  (version 20251024)
  (generator "kicad_symbol_editor")
  (generator_version "10.0")
  (symbol "Nazev_Soucastky"
    (exclude_from_sim no)
    (in_bom no)
    (on_board yes)
    (in_pos_files yes)
    (duplicate_pin_numbers_are_jumpers no)
    (property "Reference" "#G" (at 0 6 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
    (property "Value" "Nazev_Soucastky" (at 0 -6 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
    (property "Footprint" "Knihovna:Nazev_Soucastky" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
    (symbol "Nazev_Soucastky_0_1"
      (arc (start X1 Y1) (mid Xm Ym) (end X2 Y2) (stroke (width 0.254) (type default) (color 0 0 0 1)) (fill (type none)))
      (polyline (pts (xy X1 Y1) (xy X2 Y2)) (stroke (width 0.254) (type default) (color 0 0 0 1)) (fill (type none)))
    )
    (embedded_fonts no)
  )
)
```

### Pouzdro v `.kicad_mod` (v knihovně `.pretty`)
```lisp
(footprint "Nazev_Soucastky"
  (version 20260206)
  (generator "kicad_footprint_editor")
  (generator_version "10.0")
  (layer "F.Cu")
  (property "Reference" "REF**" (at 0 -6 0) (layer "F.SilkS") (hide yes) (uuid "00000000-0000-0000-0000-000000000001")
    (effects (font (size 1 1) (thickness 0.15)))
  )
  (property "Value" "Nazev_Soucastky" (at 0 6 0) (layer "F.Fab") (hide yes) (uuid "00000000-0000-0000-0000-000000000002")
    (effects (font (size 1 1) (thickness 0.15)))
  )
  (duplicate_pad_numbers_are_jumpers no)
  (fp_arc (start X1 Y1) (mid Xm Ym) (end X2 Y2) (stroke (width 0.15) (type default)) (layer "F.SilkS") (uuid "00000000-0000-0000-0000-000000000003"))
  (fp_line (start X1 Y1) (end X2 Y2) (stroke (width 0.15) (type default)) (layer "F.SilkS") (uuid "00000000-0000-0000-0000-000000000004"))
  (embedded_fonts no)
)
```

> [!WARNING]
> Pozor na uzavírání závorek u `fp_arc` a `fp_line`! Atributy `(stroke ...)` a `(layer ...)` musí být **uvnitř** těla prvku před jeho koncovou závorkou.

## 3. Registrace knihoven v projektu
V podsložce projektu (např. `kicad/antena1/`) vytvoř:
- `sym-lib-table`:
  ```lisp
  (sym_lib_table
    (version 7)
    (lib (name "Logo")(type "KiCad")(uri "${KIPRJMOD}/../Logo.kicad_sym")(options "")(descr "Logo Library"))
  )
  ```
- `fp-lib-table`:
  ```lisp
  (fp_lib_table
    (version 7)
    (lib (name "Logo")(type "KiCad")(uri "${KIPRJMOD}/../Logo.pretty")(options "")(descr "Logo Footprint Library"))
  )
  ```

## 4. Validace přes Docker KiCad CLI
Ověření správnosti syntaxe a vizuální kontrola exportem do SVG:
```bash
docker compose --profile kicad-export run --rm kicad sh -c "
  kicad-cli sym export svg -o /workspace/export/ /workspace/kicad/Logo.kicad_sym &&
  kicad-cli fp export svg -o /workspace/export/ /workspace/kicad/Logo.pretty
"
```
