"""Compose AgentScope's application with AgentHarbor tenancy."""
import os
from pathlib import Path
import secrets

from dotenv import load_dotenv
from agentscope.app import create_app
from agentscope.app.channel import DingTalkChannel, DiscordChannel, FeishuChannel
from agentscope.app.hub import ClawSkillHub, GitHubMCPHub
from agentscope.app.message_bus import InMemoryMessageBus
from agentscope.app.rag.knowledge_base_manager import CollectionPerKbManager
from agentscope.app.storage import AsyncSQLAlchemyStorage
from agentscope.middleware import AgenticMemoryMiddleware
from agentscope.rag import ApproxTokenChunker, QdrantStore

from .auth import install_auth
from .mobile import router as mobile_router
from .workspaces import TenantWorkspaceManager

ROOT = Path(__file__).resolve().parents[3]


async def memory_factory(user_id, agent_id, session_id, workspace):
    return [AgenticMemoryMiddleware(workdir=workspace.workdir, backend=workspace.get_backend())]


def create_harbor_app(data_dir=None):
    load_dotenv(ROOT / '.env')
    data = Path(data_dir or os.getenv('HARBOR_DATA_DIR', str(ROOT / 'data'))).resolve()
    data.mkdir(parents=True, exist_ok=True)
    secret_file = data / 'download.secret'
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    storage = AsyncSQLAlchemyStorage(f"sqlite+aiosqlite:///{(data / 'agents.sqlite3').as_posix()}")
    app = create_app(
        title='AgentHarbor · 智港',
        storage=storage,
        message_bus=InMemoryMessageBus(),
        workspace_manager=TenantWorkspaceManager(data / 'workspaces'),
        knowledge_base_manager=CollectionPerKbManager(storage=storage, vector_store=QdrantStore(path=str(data / 'vectors'))),
        knowledge_chunkers=[ApproxTokenChunker],
        mcp_hubs=[GitHubMCPHub()],
        skill_hubs=[ClawSkillHub(api_token=os.getenv('CLAWHUB_API_TOKEN'))],
        channels=[DingTalkChannel, DiscordChannel, FeishuChannel],
        extra_agent_middlewares=memory_factory,
        download_secret=secret_file.read_text(encoding='utf-8').strip(),
    )
    app.include_router(mobile_router)
    install_auth(
        app, data / 'identity.sqlite3',
        allowed_origins=set(os.getenv('HARBOR_ALLOWED_ORIGINS', 'http://localhost:5177,http://127.0.0.1:5177,http://localhost:8081,http://127.0.0.1:8081,http://localhost:8017,http://127.0.0.1:8017,tauri://localhost,http://tauri.localhost,https://tauri.localhost').split(',')),
        registration_enabled=os.getenv('HARBOR_ALLOW_REGISTRATION', 'true').lower() == 'true',
        secure_cookie=os.getenv('HARBOR_SECURE_COOKIE', 'false').lower() == 'true',
    )
    return app
