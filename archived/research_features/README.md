# Research Feature Archive

This folder contains the heavy research features removed from the active Heimdall Core app.

Archived scope:
- Backtest center and run detail pages
- Strategy editor and strategy contracts
- Factor research pages and services
- Paper run lifecycle and managers
- Freqtrade execution, report, and strategy generation services
- Related routers, runtime service definitions, persistence repositories, tests, and frontend modules

This archive is intentionally not wired into the active app. It is kept only so a future human or AI agent can inspect what the separated research functionality used to do.

The active app should not import from this folder. If any feature is restored later, move it back through an explicit migration instead of importing archived code in place.
