from app.contracts.chart_workspace import WorkspaceWrite
from app.infra import research_files
from app.services.chart_workspace_store import ChartWorkspaceStore


def test_saved_absolute_paths_resolve_after_project_and_runtime_rename(tmp_path, monkeypatch):
    root = tmp_path / 'OpenTrading'
    artifact = root / '.opentrading_runtime' / 'runs' / 'saved.json'
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"saved": true}', encoding='utf-8')
    monkeypatch.setattr(research_files, 'BASE_DIR', root)
    old = tmp_path / 'Heimdall' / '.heimdall_runtime' / 'runs' / 'saved.json'

    assert research_files.relocated_project_path(old) == artifact
    assert research_files.read_json(old) == {'saved': True}
    assert research_files.file_hash(old) == research_files.file_hash(artifact)
    unrelated = tmp_path / 'unrelated' / 'saved.json'
    assert research_files.relocated_project_path(unrelated) == unrelated


def test_existing_paths_keep_their_original_evidence(tmp_path, monkeypatch):
    old = tmp_path / 'Heimdall' / 'original.json'
    old.parent.mkdir()
    old.write_text('original', encoding='utf-8')
    monkeypatch.setattr(research_files, 'BASE_DIR', tmp_path / 'OpenTrading')
    assert research_files.relocated_project_path(old) == old


def test_renamed_builtin_preserves_saved_revisions_and_custom_scripts(tmp_path):
    store = ChartWorkspaceStore(tmp_path)
    original = store.put('scripts', 'heimdall-v7-2', WorkspaceWrite(
        name='Heimdall original', data={'source': 'original source'}), readonly=True)
    custom = store.put('scripts', 'custom', WorkspaceWrite(name='My script', data={'source': 'my source'}))
    store.seed()
    store.seed()

    scripts = store.list('scripts')
    assert {item.id for item in scripts} == {'opentrading-v7-2', 'custom'}
    assert store.get('scripts', 'opentrading-v7-2').name.startswith('OpenTrading')
    assert store.get('scripts', 'heimdall-v7-2', original.version) == original
    assert store.get('scripts', 'custom') == custom
