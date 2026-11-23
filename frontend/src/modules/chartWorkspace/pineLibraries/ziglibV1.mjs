// This file carries DevLucem’s ZigLib v1 under MPL-2.0.
// https://mozilla.org/MPL/2.0/ — © DevLucem
// Original source: https://www.tradingview.com/script/NC3cgEcT-ZigLib/

export const zigLibV1 = Object.freeze({
  id: "DevLucem/ZigLib/1",
  sourceUrl: "https://www.tradingview.com/script/NC3cgEcT-ZigLib/",
  license: "MPL-2.0",
  sourceSha256: "9d78cfa7e92eaa3e403eb905a0ae28ee0f97e578e8a1ca659b29be209cae9baf",
  source: `// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © DevLucem

//@version=5
library("ZigLib", overlay=true)

export zigzag (float _low=low, float _high=high, int depth=12, int deviation=5, int backstep=2) =>
    hr = ta.barssince(not (_high[-ta.highestbars(depth)] - _high > deviation*syminfo.mintick)[1])
    lr = ta.barssince(not (_low - _low[-ta.lowestbars(depth)] > deviation*syminfo.mintick)[1])
    direction = ta.barssince(not (hr > lr)) >= backstep? -1: 1

    var chart.point z = chart.point.now(_low)
    var chart.point z1 = chart.point.now(_low)
    var chart.point z2 = chart.point.now(_high)

    if ta.change(direction)
        z1 := z2.copy()
        z2 := z.copy()

    if direction>0
        if  _high > z2.price
            z2 := chart.point.now(_high)
            z := chart.point.now(_low)
        if _low < z.price
            z := chart.point.now(_low)

    if direction<0
        if _low < z2.price
            z2 := chart.point.now(_low)
            z := chart.point.now(_high)
        if _high > z.price
            z := chart.point.now(_high)

    [direction, z1, z2]
    
[direction, z1, z2] = request.security(syminfo.tickerid, input.timeframe("240", "Resolution"), zigzag())
bgcolor(direction<0? color.rgb(255, 82, 82, 80): color.rgb(0, 230, 119, 80))

line zz = line.new(z1.time, z1.price, z2.time, z2.price, xloc.bar_time, width=3)
if direction==direction[1]
    line.delete(zz[1])`,
})
