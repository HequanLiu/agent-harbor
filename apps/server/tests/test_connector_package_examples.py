import io
import json
import zipfile

import pytest
from cryptography.fernet import Fernet
from harbor.connectors.package import read_package
from harbor.connectors.store import ConnectorStore
from test_connectors import package


def with_metadata(**updates):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package())) as source, zipfile.ZipFile(output, 'w') as dest:
        for name in source.namelist():
            value = source.read(name)
            if name == 'connector-meta.json':
                value = json.dumps({**json.loads(value), **updates})
            dest.writestr(name, value)
    return output.getvalue()


def test_business_source_does_not_require_client_named_skill():
    result = read_package(with_metadata(source='dresscode-mes'))
    assert list(result['skills']) == ['test-skill']


def test_examples_are_supplied_by_connector_and_survive_store_restart(tmp_path):
    key = Fernet.generate_key()
    path = tmp_path / 'connectors.db'
    store = ConnectorStore(path, key)
    store.install('tenant', 'owner', read_package(with_metadata(examples=['创建商机', '查询联系人'])))
    assert ConnectorStore(path, key).list('tenant', 'owner')[0]['examples'] == ['创建商机', '查询联系人']


@pytest.mark.parametrize('examples', ['text', {}, [None], [''], ['x' * 1001], ['x'] * 9])
def test_invalid_examples_are_rejected(examples):
    with pytest.raises(ValueError):
        read_package(with_metadata(examples=examples))
