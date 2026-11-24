import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { runPineComputation } from '../src/modules/chartWorkspace/pineComputation.mjs'

const folder = process.argv[2]
const reportOnly = process.argv.includes('--report')
let pipedInput
if (process.argv.includes('--managed')) {
  const bytes = []
  for await (const chunk of process.stdin) bytes.push(chunk)
  const input = Buffer.concat(bytes)
  if (input[0] !== 49 || (!reportOnly && input.length !== 1)) process.exit(2)
  if (reportOnly) pipedInput = JSON.parse(input.subarray(1).toString('utf8'))
}
const write = (name, value) => {
  if (reportOnly && ['metadata.json', 'series.json'].includes(name)) return
  const target = path.join(folder, name)
  fs.writeFileSync(target + '.tmp', JSON.stringify(value))
  fs.renameSync(target + '.tmp', target)
}
const hash = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex')
try {
  const input = pipedInput ?? JSON.parse(fs.readFileSync(path.join(folder, 'input.json'), 'utf8'))
  const result = await runPineComputation(input, { write, hash, runtimeVersion: process.version, reportOnly })
  if (input.prepareOnly) process.exit(0)
  const { summary, provenance } = result
  if (reportOnly) {
    const emit = async frame => {
      if (!process.stdout.write('OPENTRADING_REPORT\t' + JSON.stringify(frame) + '\n')) {
        await new Promise(resolve => process.stdout.once('drain', resolve))
      }
    }
    for (const kind of ['equity', 'trades', 'open_trades', 'warnings']) {
      for (let offset = 0; offset < result[kind].length; offset += 1024) {
        await emit({kind, items:result[kind].slice(offset, offset + 1024)})
      }
    }
    await emit({kind:'summary', summary, provenance:{...result.provenance, recording:'report'}})
  } else write('result.json', result)
} catch (error) {
  write('error.json',{error:error.message,stack:error.stack})
  process.exitCode = 1
}
