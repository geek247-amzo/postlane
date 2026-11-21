import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('postlane_sync_secrets',Path(__file__).resolve().parents[1]/'scripts/sync_secrets.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_optional_mount_files_exist_without_enabling_integrations(tmp_path):
    (tmp_path/'.env').write_text('POSTGRES_PASSWORD=synthetic-db\nENCRYPTION_KEY=synthetic-encryption\nBOOTSTRAP_TOKEN=synthetic-bootstrap\n')
    module.sync(tmp_path)
    assert (tmp_path/'secrets/mailcow_api_key').read_text()==''
    assert (tmp_path/'secrets/push_vapid_private_key').read_text()==''
    assert (tmp_path/'secrets').stat().st_mode & 0o777 == 0o700
    (tmp_path/'secrets/mailcow_api_key').write_text('preserve-synthetic-existing')
    module.sync(tmp_path)
    assert (tmp_path/'secrets/mailcow_api_key').read_text()=='preserve-synthetic-existing'


def test_optional_secret_symlink_is_rejected(tmp_path):
    (tmp_path/'.env').write_text('POSTGRES_PASSWORD=synthetic-db\nENCRYPTION_KEY=synthetic-encryption\nBOOTSTRAP_TOKEN=synthetic-bootstrap\n')
    directory=tmp_path/'secrets';directory.mkdir()
    (directory/'mailcow_api_key').symlink_to(tmp_path/'unrelated')
    with pytest.raises(SystemExit):module.sync(tmp_path)
