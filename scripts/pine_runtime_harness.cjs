// Generate an observer-only TradingView harness from the delivered Pine source.
// The original file is never overwritten. Only the OHLC input series is replaced.
function makeHarness(source, rows, expected) {
  const replacements = {open: '_o', high: '_h', low: '_l', close: '_c', hl2: '((_h + _l) / 2)'};
  let pine = source.replace(/"[^"\n]*"|\/\/[^\n]*|\b(?:open|high|low|close|hl2)\b/g,
    token => replacements[token] || token);
  const once = (from, to) => {
    if (pine.split(from).length !== 2) throw new Error('Observer anchor must be unique: ' + from);
    pine = pine.replace(from, to);
  };
  once('        stoppedOut := true\n        side := 0\n    if closeNext',
       '        observe(3, currentOpen)\n        stoppedOut := true\n        side := 0\n    if closeNext');
  once('    if closeNext\n        if side == 1',
       '    if closeNext\n        if side != 0\n            observe(3, currentOpen)\n        if side == 1');
  once('                side := direction\n                entryPrice := fillPrice',
       '                observe(direction == 1 ? 1 : 2, fillPrice)\n                side := direction\n                entryPrice := fillPrice');
  once('    if side != 0 and (side == 1 ? currentLow <= stopPrice : currentHigh >= stopPrice)\n        stoppedOut := true',
       '    if side != 0 and (side == 1 ? currentLow <= stopPrice : currentHigh >= stopPrice)\n        observe(3, stopPrice)\n        stoppedOut := true');
  const array = (name, values) => `var ${name} = array.from(${values.join(',')})\n`;
  const header = '\n// VALIDATION ONLY: 650 warmup bars, then 240 fixed OHLC bars.\n' +
    ['oo', 'hh', 'll', 'cc'].map((n, i) => array(n, rows.map(r => Number(r[i]).toFixed(4)))).join('') +
    array('eb', expected.map(r => r[0])) + array('ea', expected.map(r => r[1])) + array('ep', expected.map(r => Number(r[2]).toFixed(8))) + `
int fixtureIndex = bar_index - 650
int safeIndex = math.max(0, math.min(239, fixtureIndex))
float _o = fixtureIndex < 0 ? 100.0 : array.get(oo, safeIndex)
float _h = fixtureIndex < 0 ? 100.2 : array.get(hh, safeIndex)
float _l = fixtureIndex < 0 ? 99.8 : array.get(ll, safeIndex)
float _c = fixtureIndex < 0 ? 100.0 : array.get(cc, safeIndex)
var counts = array.new_int(2, 0)
var actualEvents = array.new_string()
var failures = array.new_string()
observe(int action, float price) =>
    if bar_index >= 650 and bar_index < 890
        int cursor = array.get(counts, 0)
        bool matches = false
        if cursor < array.size(eb)
            matches := bar_index == array.get(eb, cursor) and action == array.get(ea, cursor) and math.abs(price - array.get(ep, cursor)) <= 0.0000001
        string eventText = str.tostring(bar_index) + ":" + str.tostring(action) + ":" + str.tostring(price, "#.########")
        array.push(actualEvents, eventText)
        if not matches
            array.set(counts, 1, array.get(counts, 1) + 1)
            if array.size(failures) < 5
                array.push(failures, eventText)
        array.set(counts, 0, cursor + 1)
    0
`;
  once('indicator("Heimdall ETH · EMA55 · 当前周期 v7.2", overlay=true)',
       'indicator("Heimdall v7.2 runtime validation", overlay=true)' + header);
  pine += `
// Validation output only; no production trading logic is changed.
var int checkedBars = 0
if bar_index >= 650 and bar_index < 890 and barstate.isconfirmed
    checkedBars += 1
bool passed = checkedBars == 240 and array.get(counts, 0) == array.size(eb) and array.get(counts, 1) == 0
string summary = (passed ? "PASS" : "FAIL") + " | bars=" + str.tostring(checkedBars) + " | events=" + str.tostring(array.get(counts, 0)) + "/" + str.tostring(array.size(eb)) + " | mismatches=" + str.tostring(array.get(counts, 1))
if bar_index == 889 and barstate.isconfirmed
    log.info(summary)
    log.info(array.join(actualEvents, ";"))
var report = table.new(position.middle_center, 1, 2, bgcolor=color.black)
if barstate.islast
    table.cell(report, 0, 0, summary, text_color=passed ? color.lime : color.red, text_size=size.large)
    table.cell(report, 0, 1, "Synthetic historical OHLC; price tolerance 1e-7\\n" + array.join(failures, ";"), text_color=color.white)
`;
  return pine;
}

if (typeof module !== 'undefined') module.exports = {makeHarness};
if (typeof require !== 'undefined' && require.main === module) {
  const fs = require('node:fs');
  const crypto = require('node:crypto');
  const root = require('node:path').resolve(__dirname, '..');
  const folder = root + '/docs/verification/pine-v7-2-contract/';
  const source = fs.readFileSync(root + '/strategies/pine/eth_ema55_manual_chart_v7_2.pine', 'utf8').replace(/\r\n/g, '\n');
  const fixture = JSON.parse(fs.readFileSync(folder + 'runtime-fixture-20260920.json', 'utf8'));
  const pine = makeHarness(source, fixture.bars, fixture.expected_fills);
  fs.writeFileSync(folder + 'runtime-harness-20260920.pine', pine, 'utf8');
  let fnv = 2166136261;
  for (let i = 0; i < pine.length; i++) fnv = Math.imul(fnv ^ pine.charCodeAt(i), 16777619) >>> 0;
  console.log(JSON.stringify({characters: pine.length, fnv: fnv.toString(16), sha256: crypto.createHash('sha256').update(pine).digest('hex')}));
}
