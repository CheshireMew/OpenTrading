# Bitcoin Halving Cycle Chart Implementation Plan

## Goal Description

Add a new visualization tool to help users analyze Bitcoin price trends relative to its halving cycles.
The interface will show a logarithmic price chart with overlaid halving dates and a cycle progress indicator.

## User Review Required

None (Standard feature addition).

## Proposed Changes

### 1. Frontend

#### [NEW] [src/views/tools/Halving.vue](file:///e:/Work/Code/Heimdall/frontend/src/views/tools/Halving.vue)

- **Layout**: Top summary cards (Days until next halving, Cycle progress), Main Chart.
- **Logic**:
  - Fetch full BTC/USDT history (Daily) via existing API `dca.py` (or new endpoint?).
  - Can reuse `DCACalculator`'s data fetching or just call generic market API.
  - Existing `api/market.py` might need an endpoint for "full history" without DCA simulation overhead.
- **Chart**: Uses `chart.js`. Logarithmic scale. Vertical lines at:
  - 2012-11-28
  - 2016-07-09
  - 2020-05-11
  - 2024-04-20
  - 2028-04-17 (Est)

#### [MODIFY] [src/router/index.ts](file:///e:/Work/Code/Heimdall/frontend/src/router/index.ts)

- Add route `/tools/halving`.

#### [MODIFY] [src/App.vue](file:///e:/Work/Code/Heimdall/frontend/src/App.vue) (or Sidebar component)

- Add link to the sidebar menu.

### 2. Backend

No new complex logic needed, but might need a clean way to get max history.

- Current `dca_calculator.py` logic fetches ranges.
- I'll check `api/market.py` to see if there is a generic K-line endpoint. If not, I'll add one.

### 3. Visualization Design

I propose two possible views for this chart. We can implement the "Timeline View" first as it is the standard.

#### Option A: Logarithmic Timeline (The Standard)

- **X-Axis**: Time (2010 - 2030).
- **Y-Axis**: Price (Logarithmic Scale).
- **Features**:
  - **Vertical Lines**: Marking each Halving Date.
  - **Color Zoning**:
    - 🟥 **Red Zone** (6-18 months after halving): Historically "Bull Run / Bubble" phase.
    - 🟩 **Green Zone** (6-12 months before halving): Historically "Accumulation" phase.
  - **Countdown**: A prominent counter showing "Days to Next Halving".

#### Option B: Cycle Overlay (Epoch Comparison)

- **X-Axis**: "Days Since Halving" (Day 0 to Day 1460).
- **Y-Axis**: ROI % (Percentage Growth from Halving Day).
- **Features**:
  - Overlays Cycle 1 (2012), Cycle 2 (2016), Cycle 3 (2020), and Current Cycle (2024) on top of each other.
  - This allows answering: _"Are we moving faster or slower than previous cycles?"_

## Verification Plan

1.  **Run Frontend**: Verify page loads.
2.  **Check Chart**: Verify Log scale works (essential for long term BTC).
3.  **Verify Dates**: Check vertical lines align with price dips/rises correctly.
