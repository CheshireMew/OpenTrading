# Third-party notices

## Python and JavaScript dependencies

Runtime dependencies are not vendored by OpenTrading and retain their respective licenses. Exact Python resolution metadata is recorded in `pdm.lock` and `requirements.lock`; exact frontend dependency resolution is recorded in `frontend/package-lock.json`.

## Bundled Pine libraries

`frontend/src/modules/chartWorkspace/pineLibraries/ziglibV1.mjs` carries the original [DevLucem/ZigLib/1](https://www.tradingview.com/script/NC3cgEcT-ZigLib/) source, © DevLucem, under [Mozilla Public License 2.0](https://mozilla.org/MPL/2.0/). The source and its original notice are retained verbatim, with SHA-256 `9d78cfa7e92eaa3e403eb905a0ae28ee0f97e578e8a1ca659b29be209cae9baf`. `pineLibraries.mjs` provides the host's import resolution and equivalent expression normalization for PineTS 0.9.34; the bundled library and user Pine documents retain their original source.

## Financial data

Bundled and downloaded financial data is not covered by OpenTrading's AGPL grant. See `data/README.md` and the in-product source labels for provenance and quality boundaries.
