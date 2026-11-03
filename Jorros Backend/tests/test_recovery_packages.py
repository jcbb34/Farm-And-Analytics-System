"""Recovery round trips use isolated databases and generated photos only."""
from pathlib import Path
import json
from hashlib import sha256
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, event, func, inspect, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm, submit, review
from app.core.database import Base
from app.models import CropGrowthRecord, TaskEvidence, SystemBackup
from app.routers.backups import router as backup_router
from app.services import backup_service
from app.services.evidence_storage import get_evidence_storage
from app.services.recovery_service import RecoveryError, inspect_recovery_package, restore_recovery_package


@pytest.fixture
def backup(farm, tmp_path, monkeypatch):
    version = Table('alembic_version', MetaData(), Column('version_num', String(32), primary_key=True))
    version.create(farm.engine)
    with farm.engine.begin() as connection:
        connection.execute(version.insert().values(version_num='e5f6a7b8c9d0'))
    response, _ = submit(farm, 'Crop')
    assert response.status_code == 200,response.text
    assert review(farm, 'Crop').status_code == 200
    monkeypatch.setattr(backup_service, 'engine', farm.engine)
    monkeypatch.setattr(backup_service, 'BACKUP_FOLDER', tmp_path / 'backups')
    farm.client.app.include_router(backup_router)
    response = farm.client.post('/api/v1/backups', headers=farm.headers['manager'])
    assert response.status_code == 201,response.text
    farm.backup_id = response.json()['id']
    farm.backup_response = response.json()
    with Session(farm.engine) as db:
        farm.package = Path(db.get(SystemBackup, farm.backup_id).storage_path).with_suffix('.recovery.zip')
    return farm


def test_database_and_photo_round_trip_into_new_target(backup,tmp_path):
    data=inspect_recovery_package(backup.package)
    assert len(data['recovery']['evidence_files']) == 2
    assert backup.backup_response['recovery_available']
    legacy=backup.client.get(f'/api/v1/backups/{backup.backup_id}/content',headers=backup.headers['manager'])
    assert legacy.status_code==200 and legacy.json()['format_version']=='1.0'
    response=backup.client.get(f'/api/v1/backups/{backup.backup_id}/recovery-package',headers=backup.headers['manager'])
    assert response.status_code==200 and response.headers['content-type']=='application/zip'
    assert response.content==backup.package.read_bytes()
    assert backup.client.get(f'/api/v1/backups/{backup.backup_id}/recovery-package',headers=backup.headers['worker']).status_code==403
    target=create_engine(f'sqlite+pysqlite:///{tmp_path / "restored.db"}')
    evidence=tmp_path/'restored-evidence'
    dry=restore_recovery_package(backup.package,target,evidence,initialize=True)
    assert not dry['applied'] and inspect(target).get_table_names()==[] and not evidence.exists()
    result=restore_recovery_package(backup.package,target,evidence,apply=True,initialize=True)
    assert result['applied'] and result['evidence_files']==2
    with Session(target) as db:
        assert db.scalar(select(func.count()).select_from(CropGrowthRecord))==1
        photo=db.scalar(select(TaskEvidence))
        assert sha256((evidence/photo.storage_identifier).read_bytes()).hexdigest()==photo.sha256
        assert (evidence/photo.thumbnail_storage_identifier).is_file()
    # Existing rows are never replaced by a retry or an incorrect recovery command.
    with pytest.raises(RecoveryError):
        restore_recovery_package(backup.package,target,tmp_path/'second-evidence',apply=True)
    target.dispose()


def _rewrite(package, target, transform=None, extra=None):
    with ZipFile(package) as source:
        contents={name:source.read(name) for name in source.namelist()}
    if transform:
        transform(contents)
    with ZipFile(target,'w',ZIP_DEFLATED) as out:
        for name,data in contents.items(): out.writestr(name,data)
        if extra: out.writestr(*extra)
    return target


@pytest.mark.parametrize('kind',['photo','database','extra-path','missing-photo','bad-count','bad-version'])
def test_tampered_or_incomplete_packages_are_rejected(backup,tmp_path,kind):
    def tamper(contents):
        photo=next(name for name in contents if name.startswith('evidence/'))
        if kind=='photo': contents[photo]=b'corrupted'
        elif kind=='database': contents['database.json']+=b' '
        elif kind=='missing-photo': del contents[photo]
        elif kind in ('bad-count','bad-version'):
            data=json.loads(contents['database.json'])
            if kind=='bad-count': data['row_count']+=1
            else: data['database']['alembic_revision']='incorrect'
            raw=json.dumps(data).encode()
            contents['database.json']=raw
            manifest=json.loads(contents['manifest.json']);manifest['database_sha256']=sha256(raw).hexdigest()
            contents['manifest.json']=json.dumps(manifest).encode()
    path=_rewrite(backup.package,tmp_path/'invalid.zip',tamper,
                  extra=('../outside-file',b'unsafe') if kind=='extra-path' else None)
    with pytest.raises(RecoveryError): inspect_recovery_package(path)
    assert not (tmp_path.parent/'outside-file').exists()


def test_missing_evidence_cannot_produce_a_completed_backup(backup):
    with Session(backup.engine) as db:
        photo=db.scalar(select(TaskEvidence))
        get_evidence_storage().path_for_response(photo.storage_identifier).unlink()
    response=backup.client.post('/api/v1/backups',headers=backup.headers['manager'])
    assert response.status_code==500
    with Session(backup.engine) as db:
        failed=db.scalar(select(SystemBackup).order_by(SystemBackup.id.desc()))
        assert failed.status=='Failed'
        assert not Path(failed.storage_path).exists()
        assert not Path(failed.storage_path).with_suffix('.recovery.zip').exists()
    # The previously completed package contains its own immutable photo bytes.
    assert inspect_recovery_package(backup.package)['recovery']['evidence_files']


def test_legacy_json_backups_still_download_without_a_recovery_claim(backup,tmp_path):
    path=backup_service.BACKUP_FOLDER/'legacy.json';raw=b'{"format_version":"1.0","legacy":true}'
    path.write_bytes(raw)
    with Session(backup.engine) as db:
        row=SystemBackup(backup_code='LEGACY-TEST',filename=path.name,storage_path=str(path),status='Completed',
                         checksum_sha256=sha256(raw).hexdigest())
        db.add(row);db.commit();record_id=row.id
    response=backup.client.get(f'/api/v1/backups/{record_id}/content',headers=backup.headers['manager'])
    assert response.status_code==200 and response.json()['legacy']
    assert backup.client.get(f'/api/v1/backups/{record_id}/recovery-package',headers=backup.headers['manager']).status_code==409
    listing=backup.client.get('/api/v1/backups',headers=backup.headers['manager']).json()
    assert not next(row for row in listing if row['id']==record_id)['recovery_available']
    assert backup.client.post('/api/v1/backups',headers=backup.headers['worker']).status_code==403
    assert backup.client.get('/api/v1/backups').status_code==401


@pytest.mark.parametrize('failure',['insert','file-install'])
def test_failed_restore_rolls_back_database_and_files_then_can_retry(backup,tmp_path,monkeypatch,failure):
    target=create_engine(f'sqlite+pysqlite:///{tmp_path / "failed.db"}')
    destination=tmp_path/'failed-evidence'
    if failure=='insert':
        def fail(connection,cursor,statement,parameters,context,executemany):
            if statement.lower().startswith('insert into crops '): raise RuntimeError('Forced insert failure')
        event.listen(target,'before_cursor_execute',fail)
    else:
        original=Path.rename
        def fail(self,dest):
            if self.name.startswith('.joross-recovery-'): raise RuntimeError('Forced file installation failure')
            return original(self,dest)
        monkeypatch.setattr(Path,'rename',fail)
    with pytest.raises(RuntimeError):
        restore_recovery_package(backup.package,target,destination,apply=True,initialize=True)
    assert inspect(target).get_table_names()==[]
    assert not destination.exists()
    assert not list(tmp_path.glob('.joross-recovery-*'))
    if failure=='insert': event.remove(target,'before_cursor_execute',fail)
    else: monkeypatch.setattr(Path,'rename',original)
    assert restore_recovery_package(backup.package,target,destination,apply=True,initialize=True)['applied']
    target.dispose()


def test_restore_refuses_live_evidence_directory_or_existing_files(backup,tmp_path):
    target=create_engine(f'sqlite+pysqlite:///{tmp_path / "safe.db"}')
    with pytest.raises(RecoveryError,match='separate'):
        restore_recovery_package(backup.package,target,get_evidence_storage().root,apply=True,initialize=True)
    destination=tmp_path/'user-files';destination.mkdir();(destination/'keep').write_text('existing')
    with pytest.raises(RecoveryError,match='empty'):
        restore_recovery_package(backup.package,target,destination,apply=True,initialize=True)
    assert (destination/'keep').read_text()=='existing'
    assert inspect(target).get_table_names()==[]
    target.dispose()


@pytest.mark.parametrize('versions', [['older-revision'], ['d4e5f6a7b8c9', 'other-head']])
def test_restore_refuses_different_revision_or_schema(backup,tmp_path,versions):
    target=create_engine(f'sqlite+pysqlite:///{tmp_path / "old.db"}')
    Base.metadata.create_all(target)
    version=Table('alembic_version',MetaData(),Column('version_num',String(32),primary_key=True))
    version.create(target)
    with target.begin() as connection:
        connection.execute(version.insert(), [{'version_num': revision} for revision in versions])
    with pytest.raises(RecoveryError,match='same Alembic revision'):
        restore_recovery_package(backup.package,target,tmp_path/'not-restored',apply=True)
    with target.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(CropGrowthRecord))==0
    target.dispose()


def test_cli_inspects_and_restores_an_isolated_database(backup,tmp_path):
    import os, subprocess, sys
    script=Path(__file__).resolve().parents[1]/'scripts/restore_backup.py'
    checked=subprocess.run([sys.executable,str(script),str(backup.package)],capture_output=True,text=True,env=os.environ.copy())
    assert checked.returncode==0,checked.stderr
    assert json.loads(checked.stdout)['valid']
    restored=subprocess.run([sys.executable,str(script),str(backup.package),'--sqlite-file',str(tmp_path/'cli.db'),
                            '--evidence-directory',str(tmp_path/'cli-evidence'),'--initialize-empty-target','--apply'],
                            capture_output=True,text=True,env=os.environ.copy())
    assert restored.returncode==0,restored.stderr
    assert json.loads(restored.stdout)['applied'] and len(list((tmp_path/'cli-evidence').iterdir()))==2
