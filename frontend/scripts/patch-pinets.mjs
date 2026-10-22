// Pinned upstream correction. Keep Node and browser ESM builds identical in
// behavior. Do not silently apply this patch to another dependency revision.
import fs from 'node:fs'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

const root = new URL('../node_modules/pinets/', import.meta.url)
const meta = JSON.parse(fs.readFileSync(new URL('package.json', root), 'utf8'))
if (meta.version !== '0.9.34') throw new Error('Revalidate PineTS patches before upgrading')
const marker = '/* OpenTrading 2026-09-20: limit fills do not receive market/stop slippage. */\n'
const builds = [
  ['pinets.min.es.js', 'Br', '02532565f418fd617d93314e3921872a528de28c6bf0105b2abb3a5b386e16c9'],
  ['pinets.min.browser.es.js', 'jr', '861ea8a6e1ecc10406d82e392d2799a9b86c9f968194a9972ec3ba7bd85a4cbf'],
]
for (const [name, fn, expected] of builds) {
  const file = new URL('dist/' + name, root)
  const original = fs.readFileSync(file, 'utf8')
  if (original.startsWith(marker)) continue
  const legacyMarker = marker.replace('OpenTrading', 'Heimdall')
  if (original.startsWith(legacyMarker)) {
    fs.writeFileSync(file, marker + original.slice(legacyMarker.length))
    continue
  }
  if (crypto.createHash('sha256').update(original).digest('hex') !== expected) throw new Error(`Unexpected upstream bytes: ${name}`)
  const replacements = [
    [`p=${fn}(t,h,p);const f=`, `p=c.type==="limit"?p:${fn}(t,h,p);const f=`],
    [`ee=${fn}(t,-h,U.price),ke=`, `ee=U.kind==="profit"?U.price:${fn}(t,-h,U.price),ke=`],
  ]
  let patched = original
  for (const [from, to] of replacements) {
    if (patched.split(from).length !== 2) throw new Error(`Patch must match exactly once: ${name}`)
    patched = patched.replace(from, to)
  }
  fs.writeFileSync(file, marker + patched)
  console.log('Applied PineTS limit-slippage correction:', fileURLToPath(file))
}
