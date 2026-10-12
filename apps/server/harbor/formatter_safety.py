"""Process-wide attachment boundary for the secret-bearing Harbor service.

Enable once, before serving requests, whenever remote connectors are enabled.
The Docker agent may read sandbox files, but model formatters on the host must
receive their contents inline: they may not resolve a client-supplied URL.
No uninstall switch is offered; a process which has held connector secrets must
not silently regain unrestricted formatter IO later in its lifetime.
"""
from functools import wraps
import inspect
from collections.abc import Mapping

from pydantic import BaseModel
from agentscope import formatter
from agentscope.formatter import FormatterBase
from agentscope.message import URLSource


class UnsafeAttachmentSource(ValueError):
    """An attachment would require the host to resolve an untrusted location."""


def _assert_inline_sources(value):
    # Inspect models directly rather than serializing: the guard also covers
    # restored history, nested tool/hint blocks, and sources assigned without
    # Pydantic revalidation. Plain text URLs are data and remain untouched.
    pending=[value]
    seen=set()
    while pending:
        current=pending.pop()
        if isinstance(current,(str,bytes,int,float,bool,type(None))):
            continue
        identity=id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current,URLSource) or (
            isinstance(current,Mapping) and current.get('type')=='url' and 'url' in current
        ):
            # Never echo the source URL/path or its contents into logs/errors.
            raise UnsafeAttachmentSource('Host model attachments must use inline base64 data; URL sources are disabled for connector isolation')
        if isinstance(current,BaseModel):
            pending.extend(vars(current).values())
        elif isinstance(current,Mapping):
            pending.extend(current.values())
        elif isinstance(current,(list,tuple,set,frozenset)):
            pending.extend(current)


def _guard(method):
    @wraps(method)
    async def format_inline(self,*args,**kwargs):
        _assert_inline_sources((args,kwargs))
        return await method(self,*args,**kwargs)
    format_inline._harbor_inline_sources=True
    return format_inline


def install_formatter_data_only_policy():
    """Guard all shipped provider entry points, including multi-agent variants.

    This is intentionally process-wide and idempotent. Call only when the
    connector service is enabled. Disabled deployments retain SDK behavior.
    Guarding just ``assert_list_of_msgs`` would miss DashScope's multi-agent
    formatter, so each public formatter entry point is protected explicitly.
    New provider exports are picked up automatically and unexpected synchronous
    entry points fail startup rather than silently weakening the boundary.
    """
    for name in formatter.__all__:
        cls=getattr(formatter,name)
        if not inspect.isclass(cls) or not issubclass(cls,FormatterBase) or cls is FormatterBase:
            continue
        method=cls.format
        if getattr(method,'_harbor_inline_sources',False):
            continue
        if not inspect.iscoroutinefunction(method):
            raise RuntimeError('Unsupported formatter entry point for connector isolation')
        cls.format=_guard(method)
