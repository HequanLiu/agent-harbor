"""Build the coding sandbox from an explicit, secret-free temporary context."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
DOCKERFILE='''FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends iptables curl ca-certificates git ripgrep nodejs npm && rm -rf /var/lib/apt/lists/*
RUN python -m venv /root/.agentscope/.venv && /root/.agentscope/.venv/bin/pip install --no-cache-dir "mcp<2" fastapi uvicorn httpx aiofiles python-frontmatter json-repair pillow docstring-parser python-dotenv typing-extensions
COPY agentscope /root/.agentscope/.venv/lib/python3.11/site-packages/agentscope
COPY _mcp_gateway_app.py /root/.agentscope/_mcp_gateway_app.py
COPY _glob_helper.py /root/.agentscope/_glob_helper.py
COPY sandbox_proxy.py /opt/harbor/sandbox_proxy.py
ENV PATH=/root/.agentscope/.venv/bin:$PATH
WORKDIR /workspace
'''

def main():
    with tempfile.TemporaryDirectory(prefix='harbor-sandbox-build-') as directory:
        target=Path(directory)
        (target/'Dockerfile').write_text(DOCKERFILE,encoding='utf-8')
        sdk=ROOT/'vendor/agentscope/src/agentscope'
        shutil.copytree(sdk,target/'agentscope',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copyfile(sdk/'workspace/_mcp_gateway/_mcp_gateway_app.py',target/'_mcp_gateway_app.py')
        shutil.copyfile(sdk/'tool/_builtin/_scripts/_glob_helper.py',target/'_glob_helper.py')
        shutil.copyfile(ROOT/'apps/server/harbor/sandbox_proxy.py',target/'sandbox_proxy.py')
        subprocess.run(['docker','build','-t','harbor-sandbox:dev',str(target)],check=True)

if __name__=='__main__':main()
