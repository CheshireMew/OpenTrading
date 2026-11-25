import { existsSync } from 'node:fs'
import { mkdir, mkdtemp } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const frontend = path.join(root, 'frontend'), args = process.argv.slice(2)
const unitOnly = args.includes('--unit'), tests = args.filter(arg => arg !== '--unit')
const env = { ...process.env }
if (!unitOnly) {
  const candidates = [env.OPENTRADING_TEST_BROWSER,
    env['ProgramFiles(x86)'] && path.join(env['ProgramFiles(x86)'], 'Microsoft/Edge/Application/msedge.exe'),
    env.ProgramFiles && path.join(env.ProgramFiles, 'Microsoft/Edge/Application/msedge.exe'),
    env.ProgramFiles && path.join(env.ProgramFiles, 'Google/Chrome/Application/chrome.exe')]
  env.OPENTRADING_TEST_BROWSER = candidates.find(candidate => candidate && existsSync(candidate))
  if (!env.OPENTRADING_TEST_BROWSER) {
    console.error('Browser integration checks require an installed Edge or Chromium browser. Set OPENTRADING_TEST_BROWSER; no browser is downloaded.')
    process.exit(1)
  }
  const testsRoot = path.join(root, '.runtime/tests')
  await mkdir(testsRoot, { recursive: true })
  const task = await mkdtemp(path.join(testsRoot, 'frontend-gate-'))
  env.OPENTRADING_CONTRACT_FIXTURES = path.join(task, 'contracts')
  env.OPENTRADING_TEST_ARTIFACTS = task
  env.OPENTRADING_TEST_PROFILE ??= path.join(root, '.runtime/cache/browser-integration')
  delete env.OPENTRADING_TEST_COLLECT
  await mkdir(env.OPENTRADING_CONTRACT_FIXTURES, { recursive: true })
  const produced = spawnSync(process.execPath, [path.join(root, 'scripts/run_backend_python.mjs'), '-m', 'pytest', '-q',
    '-o', 'addopts=--tb=short -p no:cacheprovider', '--basetemp=' + path.join(task, 'pytest'),
    'test/test_repair_contracts.py', 'test/test_pine_progress.py',
    'test/test_data_health_and_reports.py::test_health_summary_uses_metadata_for_disjoint_cold_history',
    'test/test_data_health_and_reports.py::test_history_repair_segments_large_ranges_and_reports_partial_coverage'], { cwd: root, env, stdio: 'inherit' })
  if (produced.status !== 0) process.exit(produced.status ?? 1)
} else {
  delete env.OPENTRADING_TEST_BROWSER
  console.log('Running unit checks only; use npm test for the complete browser and HTTP contract gate.')
}
// One cached, task-owned profile is reused; each test creates isolated contexts.
const result = spawnSync(process.execPath, ['--test', '--test-concurrency=1', '--test-reporter=tap', ...tests],
  { cwd: frontend, env, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
if (result.stdout) process.stdout.write(result.stdout)
if (result.stderr) process.stderr.write(result.stderr)
if (result.error) console.error(result.error.message)
const silentlySkipped = !unitOnly && /^# skipped? [1-9]/m.test(result.stdout ?? '')
if (silentlySkipped) console.error('The complete frontend gate must not skip tests.')
process.exit(result.status !== 0 || result.error || silentlySkipped ? 1 : 0)
