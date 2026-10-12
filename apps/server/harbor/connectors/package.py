"""Validate the supported WorkBuddy-style remote connector package subset.

Pure parser: no extraction, execution, authorization, or network access.
"""
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile


def read_package(content: bytes) -> dict:
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("连接器包不能超过 5 MiB")
    files = {}
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 100:
                raise ValueError("连接器文件数量超限")
            total = 0
            seen = set()
            for entry in entries:
                name = entry.filename
                path = PurePosixPath(name)
                mode = entry.external_attr >> 16
                if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                        or stat.S_ISLNK(mode) or name.casefold() in seen or "\x00" in name):
                    raise ValueError("连接器包含不安全或重复路径")
                seen.add(name.casefold())
                total += entry.file_size
                if total > 10 * 1024 * 1024 or entry.file_size > 1024 * 1024:
                    raise ValueError("连接器解压大小超限")
                if not entry.is_dir():
                    files[name] = archive.read(entry)
    except (BadZipFile, RuntimeError) as exc:
        raise ValueError("连接器压缩包无效") from exc
    try:
        meta = json.loads(files["connector-meta.json"])
        config = json.loads(files["mcp.json"])
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("缺少或损坏的连接器配置") from exc
    if not isinstance(meta, dict) or not isinstance(config, dict):
        raise ValueError("连接器配置必须为对象")
    for field,limit in (('source',80),('version',40),('name',160),('description',2000)):
        if field in meta and (not isinstance(meta[field],str) or len(meta[field])>limit):
            raise ValueError('Connector metadata must contain bounded text values')
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", meta.get("source", "")):
        raise ValueError("source 必须是小写英文唯一标识")
    if len(meta["source"]) > 80 or not re.fullmatch(r"\d+\.\d+\.\d+", meta.get("version", "")):
        raise ValueError("无效标识或版本")
    if meta.get("type", "mcp") != "mcp" or meta.get("auth_mode") is not None:
        raise ValueError("首版仅支持标准 OAuth 远程 MCP 连接器")
    if not any(n in files for n in ("icon.svg", "icon.png", "icon.jpg")):
        raise ValueError("连接器缺少图标")
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or len(servers) != 1 or set(config) != {"mcpServers"}:
        raise ValueError("一个连接器必须且只能配置一个 MCP 服务")
    item = next(iter(servers.values()))
    if not isinstance(item, dict) or set(item) - {"type", "url", "timeout", "disabledTools"}:
        raise ValueError("包含未支持的 MCP 配置，禁止预置凭据或执行命令")
    if item.get("type") != "streamableHttp":
        raise ValueError("只支持 Streamable HTTP")
    try:
        url = urlsplit(item["url"])
        valid = url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password and not url.query and not url.fragment
        url.port
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise ValueError("MCP 地址必须是不含凭据的 HTTP 或 HTTPS 地址")
    timeout = item.get("timeout", 30000)
    if type(timeout) is not int or not 1000 <= timeout <= 120000:
        raise ValueError("timeout 必须为 1000–120000 毫秒")
    disabled = item.get("disabledTools", [])
    if not isinstance(disabled, list) or any(not isinstance(v, str) for v in disabled):
        raise ValueError("disabledTools 必须是工具名称数组")
    skills = {}
    for name, value in files.items():
        match = re.fullmatch(r"skills/([a-z0-9_-]+)/SKILL\.md", name)
        if match:
            text = value.decode("utf-8-sig")
            if not text.startswith("---\n") or "\nname:" not in text or "\ndescription:" not in text:
                raise ValueError("Skill 缺少 name/description 元信息")
            import frontmatter
            document = frontmatter.loads(text)
            if document.get('name') != match[1] or not isinstance(document.get('description'), str) or not document['description'].strip():
                raise ValueError('Skill name must match its directory and description must be text')
            skills[match[1]] = text
        elif name.startswith("skills/"):
            raise ValueError("首版只加载声明的 SKILL.md，不执行包内脚本")
    if meta["source"] == "dresscode-mes" and "mes-order" not in skills:
        raise ValueError("MES 连接器必须包含订单 Skill")
    return {"metadata": meta, "mcp": {"url": item["url"], "type": "http_mcp",
            "timeout_seconds": timeout / 1000, "disabled_tools": disabled},
            "skills": skills, "sha256": hashlib.sha256(content).hexdigest()}
