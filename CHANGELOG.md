# Changelog

All notable changes to this library are documented here.

## 2.0.0 (2026-11-15)

- Fix the mirrored footprint. Version 1.0.0 placed pads 1 to 10 on the row
  where the dongle has VBUS, VDD OUT and P0.31 to P1.10, and swapped pads 11
  and 12, so a component-side-up dongle met the opposite row on every contact.
  Pads 1 to 10 and SWDIO now sit at negative y (the top row in KiCad), as in
  Nordic's top view. Boards laid out with 1.0.0 must be rerouted after updating
  the footprint.
- Draw the verification views in KiCad coordinates, so they show the footprint
  as KiCad does.
- Fail the package build when a pad sits on the wrong side of the centreline.
- Add a STEP model of the assembled dongle, attached to the footprint at its origin.
- Package the model for KiCad's Plugin and Content Manager under `3dmodels/`.

## 1.0.0 — 2026-10-23

- Add the 22-pin PCA10059 schematic symbol.
- Add the carrier-board footprint with the exact module outline.
- Add antenna and USB placement guidance.
- Add generated visual verification drawings.
- Add a GitHub Pages build for installation through KiCad's Plugin and Content Manager.

