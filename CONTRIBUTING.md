# Contributing

Corrections and improvements are welcome through GitHub issues and pull requests.

## Geometry or pinout changes

Changes to the symbol, footprint, or pin map should identify the Nordic source
file and revision used as evidence. Keep `pinout.csv`, the symbol pins, and the
footprint pad numbers synchronized.

Before opening a pull request, run:

```sh
python scripts/build_pcm.py --github-repository binloan/nrf52840-dongle-kicad
```

The command validates all 22 pins and pads and builds a local PCM repository in
`dist/`. The GitHub validation workflow performs the same check automatically.

## Publishing a new version

1. Update `VERSION` using a numeric `major.minor.patch` version.
2. Add the release notes to `CHANGELOG.md`.
3. Regenerate `visuals/` if the symbol or footprint changed.
4. Open a pull request and wait for validation to pass.
5. Merge to `main`; the Pages workflow publishes the new PCM package.

