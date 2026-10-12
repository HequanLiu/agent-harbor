"""No provider calls: test every shipped formatter before it can resolve URLs."""
import asyncio
import base64
import builtins
import inspect
import pytest
import requests
from agentscope import formatter
from agentscope.formatter import FormatterBase, OpenAIChatFormatter
from agentscope.message import Msg, DataBlock, Base64Source, URLSource, HintBlock, ToolResultBlock
from harbor.formatter_safety import install_formatter_data_only_policy, UnsafeAttachmentSource

FORMATTERS = [getattr(formatter, name) for name in formatter.__all__ if name != 'FormatterBase']

@pytest.fixture
def unguarded(monkeypatch):
    # Isolate from other application fixtures which enable the process-wide guard.
    for cls in FORMATTERS:
        monkeypatch.setattr(cls, 'format', inspect.unwrap(cls.format))

@pytest.fixture
def guarded(unguarded):
    install_formatter_data_only_policy()

def message(url, placement):
    block=DataBlock(source=URLSource(url=url,media_type='application/pdf'))
    if placement=='tool':
        return Msg(name='assistant',role='assistant',content=[ToolResultBlock(id='call',name='mes_order_source_read',output=[block],state='success')])
    if placement=='hint':
        return Msg(name='assistant',role='assistant',content=[HintBlock(hint=[block])])
    return Msg(name='user',role='user',content=[block])

@pytest.mark.parametrize('cls',FORMATTERS,ids=lambda cls:cls.__name__)
@pytest.mark.parametrize('url',['file:///harbor-sentinel.txt','http://127.0.0.1/secret','https://untrusted.example/document.pdf'])
def test_all_formatters_reject_url_before_any_io(guarded,monkeypatch,cls,url):
    def forbidden(*args,**kwargs): raise AssertionError('Formatter attempted host IO')
    monkeypatch.setattr(builtins,'open',forbidden)
    monkeypatch.setattr(requests,'get',forbidden)
    with pytest.raises(UnsafeAttachmentSource,match='inline base64'):
        asyncio.run(cls().format([message(url,'direct')]))

@pytest.mark.parametrize('cls',FORMATTERS,ids=lambda cls:cls.__name__)
@pytest.mark.parametrize('placement',['direct','tool','hint'])
def test_history_and_nested_results_are_checked(guarded,placement,cls):
    msgs=[message('file:///harbor-sentinel.txt',placement),Msg(name='user',role='user',content=[{'type':'text','text':'Continue'}])]
    with pytest.raises(UnsafeAttachmentSource) as failure: asyncio.run(cls().format(msgs))
    assert 'harbor-sentinel' not in str(failure.value)

@pytest.mark.parametrize('cls',FORMATTERS,ids=lambda cls:cls.__name__)
def test_inline_mes_images_still_format(guarded,cls):
    if cls.__name__.startswith('XAI'): pytest.importorskip('xai_sdk', reason='Optional XAI SDK is not installed; URL guard coverage still runs')
    data=base64.b64encode(b'inline-image-sentinel').decode()
    msg=Msg(name='user',role='user',content=[DataBlock(source=Base64Source(data=data,media_type='image/png'))])
    result=asyncio.run(cls(input_types=['text/plain','image/*']).format([msg]))
    assert data in str(result)

def test_disabled_policy_keeps_existing_file_behavior(unguarded,tmp_path,monkeypatch):
    sentinel=tmp_path/'fixture'/'attachment.pdf';sentinel.parent.mkdir();sentinel.write_bytes(b'non-secret-fixture');monkeypatch.chdir(tmp_path)
    # A fixture-only relative path exercises the SDK literal file:// stripping on Windows.
    result=asyncio.run(OpenAIChatFormatter(input_types=['application/pdf']).format([message('file://fixture/attachment.pdf','direct')]))
    assert base64.b64encode(sentinel.read_bytes()).decode() in str(result)

def test_install_is_idempotent_and_audits_mutated_sources(guarded):
    before=OpenAIChatFormatter.format;install_formatter_data_only_policy();assert before is OpenAIChatFormatter.format
    msg=message('https://untrusted.example/document.pdf','direct')
    msg.content[0].source={'type':'url','url':'file:///sentinel','media_type':'application/pdf'}
    with pytest.raises(UnsafeAttachmentSource): asyncio.run(OpenAIChatFormatter().format([msg]))
