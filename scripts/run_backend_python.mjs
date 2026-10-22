import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const command = process.argv[2]
const args = process.argv.slice(3)

if (!command) {
  console.error('Usage: node scripts/run_backend_python.mjs <script.py|-m module|-c code> [...args]')
  process.exit(2)
}

const isPathLike = (candidate) =>
  path.isAbsolute(candidate) || candidate.includes('/') || candidate.includes('\\')

const commandExists = (command) => {
  const result = spawnSync(command, ['--version'], {
    cwd: repoRoot,
    stdio: 'ignore',
    shell: false,
  })
  return !result.error
}

const configuredPython = process.env.OPENTRADING_PYTHON?.trim()

const resolveConfiguredPython = () => {
  if (!configuredPython) {
    return null
  }

  if (isPathLike(configuredPython)) {
    const runtimePath = path.isAbsolute(configuredPython)
      ? configuredPython
      : path.resolve(repoRoot, configuredPython)
    return existsSync(runtimePath) ? runtimePath : null
  }

  return commandExists(configuredPython) ? configuredPython : null
}

const localPythonCandidates = [
  path.join(repoRoot, 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
  path.join(repoRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
]

const candidates = [
  resolveConfiguredPython(),
  ...localPythonCandidates.filter((candidate) => existsSync(candidate)),
].filter(Boolean)

const python = candidates[0]

if (!python) {
  console.error(
    'Backend Python runtime not found. Set OPENTRADING_PYTHON or create venv/.venv in the repository root.',
  )
  process.exit(1)
}

const pythonArgs = command.startsWith('-')
  ? [command, ...args]
  : [path.isAbsolute(command) ? command : path.join(repoRoot, command), ...args]

const result = spawnSync(python, pythonArgs, {
  cwd: repoRoot,
  stdio: 'inherit',
  shell: false,
})

if (result.error) {
  console.error(result.error.message)
  process.exit(1)
}

process.exit(result.status ?? 1)
