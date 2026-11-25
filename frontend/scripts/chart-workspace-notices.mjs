import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = fileURLToPath(new URL('../', import.meta.url))
const root = path.resolve(frontend, '..')
const readJson = file => JSON.parse(readFileSync(file, 'utf8'))

// The existing Vite delivery entry consumes the same manifest and notice bytes
// that repository reviewers read. A stale declaration stops that delivery.
export function chartWorkspaceNoticeAssets() {
  const manifestPath = path.join(root, 'docs/licenses/chart-workspace/manifest.json')
  const manifest = readJson(manifestPath), lock = readJson(path.join(frontend, 'package-lock.json'))
  const assets = [{ fileName: 'licenses/chart-workspace/manifest.json', source: readFileSync(manifestPath) }]
  for (const item of manifest) {
    const folder = path.join(frontend, 'node_modules', item.package), actual = readJson(path.join(folder, 'package.json'))
    const locked = lock.packages['node_modules/' + item.package]
    if (item.version !== actual.version || item.version !== locked?.version || item.license !== actual.license
      || JSON.stringify(item.repository) !== JSON.stringify(actual.repository)) throw new Error(`Stale third-party declaration: ${item.package}`)
    const noticeFolder = path.resolve(root, ...item.notices.split(/[\\/]/))
    for (const name of readdirSync(folder).filter(name => /^(license|notice|thirdpartynotices)(\.|$)/i.test(name))) {
      const source = readFileSync(path.join(noticeFolder, name))
      if (!source.equals(readFileSync(path.join(folder, name)))) throw new Error(`Stale third-party notice: ${item.package}/${name}`)
      assets.push({ fileName: `licenses/chart-workspace/${path.basename(noticeFolder)}/${name}`, source })
    }
  }
  return assets
}

export function chartWorkspaceNotices() {
  return { name: 'chart-workspace-notices', apply: 'build', buildStart() {
    for (const asset of chartWorkspaceNoticeAssets()) this.emitFile({ type: 'asset', ...asset })
  } }
}
