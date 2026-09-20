"""Prepare one immutable dataset per batch/input group, with crash recovery."""
from contextlib import contextmanager
import errno
import time
from app.infra.research_files import lock, read_json, atomic_json, file_hash, native_path


@contextmanager
def shared_batch_data(service, run, folder, metadata):
    batch, group = metadata.get('parameter_sweep_id'), metadata.get('batch_snapshot_group')
    if not batch or not group:
        yield folder
        return
    shared = native_path(service.root.parent/'parameter_sweep_data'/batch/group)
    while True:
        owner=lock(shared)
        try:
            owner.__enter__()
            break
        except OSError as exc:
            if exc.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):raise
            if service.repository.get(run['id'])['status'] not in {'preparing','running','saving'}:
                raise InterruptedError('批量回测已取消')
            time.sleep(.2)
    try:
        files=[('data.json','data_hash')]
        if run['config'].get('execution_timeframe'):files.append(('execution_data.json','execution_data_hash'))
        manifest=shared/'manifest.json'
        seed=metadata.get('batch_seed_run')
        origin=shared if manifest.exists() else service.directory(seed) if seed else None
        known=read_json(manifest) if manifest.exists() else read_json(origin/'metadata.json') if origin else {}
        if origin:
            for name,key in files:
                origin_path = service.datasets.resolve(origin, name)
                if file_hash(origin_path)!=known.get(key):raise ValueError('批量共享行情快照校验失败')
                local_path = service.datasets.resolve(folder, name)
                if local_path.exists():
                    if file_hash(local_path)!=known[key]:raise ValueError('本次行情与批量冻结行情不同')
                else:service.datasets.install(folder, name, origin_path, known[key])
                metadata[key]=known[key]
        yield shared
        # Only publish after the existing worker validated both native and fine
        # histories. A failed preparation cannot poison later combinations.
        if not manifest.exists():
            hashes={}
            for name,key in files:
                path = service.datasets.resolve(folder, name)
                hashes[key]=file_hash(path)
                if hashes[key]!=metadata.get(key):raise ValueError('发布共享行情时校验失败')
                service.datasets.install(shared, name, path, hashes[key])
            atomic_json(manifest,hashes)
    finally:
        owner.__exit__(None,None,None)
