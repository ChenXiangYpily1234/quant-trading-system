"""JSON-RPC stdio bridge to an independently installed Codex App Server.

The wire methods and shapes follow the imported codex-main app-server-protocol
v2 schema. This module does not implement an LLM loop or synthesize responses.
"""

import asyncio
import json
import os
import tempfile
import time
import tomllib
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List

from ..agent_tools import invoke, tool_specs
from ..agent_tools.registry import TOOLS
from ..agent_tools.schemas import failure
from ..db.database import connect, initialize

_INSTRUCTIONS = """You are QuantFlow's financial research assistant. Use only the supplied
QuantFlow tools for financial facts and calculations. Never access a database,
shell, file, browser, external connector, or trading service. Do not invent data.
SIMULATED or STALE data and sample news cannot support a real financial claim.
Never generate or alter signal/risk scores, backtest metrics, holdings, or a
production strategy. Separate facts, inference, and uncertainty; include tool
provenance and state insufficient_evidence when evidence is missing. Do not
provide buy/sell or position instructions. Research drafts are not deployment.
"""

_DISABLED_FEATURES = {key: False for key in (
    "shell_tool", "view_image", "code_mode", "apply_patch_freeform",
    "web_search_request", "web_search_cached", "standalone_web_search",
    "apps", "enable_mcp_apps", "plugins", "browser_use", "computer_use",
    "image_generation", "collaboration_modes")}
_SKILL_ROOT = Path(__file__).resolve().parents[3] / "skills"
_RESEARCH_SKILLS = frozenset({"market-researcher", "signal-auditor",
    "backtest-auditor", "strategy-researcher", "portfolio-analyst", "backtest-red-team"})


def _disabled_mcp_servers() -> Dict[str, bool]:
    """Disable globally configured MCP servers in this research thread."""
    config_home = Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex")))
    path = config_home / "config.toml"
    if not path.exists():
        return {}
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AgentUnavailable("无法检查 Codex MCP 配置，Agent 已封锁") from exc
    if any("." in name for name in config.get("mcp_servers", {})):
        raise AgentUnavailable("存在无法安全禁用的 MCP 服务名，Agent 已封锁")
    return {f"mcp_servers.{name}.enabled": False
            for name in config.get("mcp_servers", {})}


class AgentUnavailable(RuntimeError):
    pass


class CodexAppServerRuntime:
    def __init__(self, executable: str = "codex"):
        self.executable = executable
        self.process = None
        self._reader_task = None
        self._stderr_task = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._workspace = None
        self._threads = set()
        self._events = defaultdict(lambda: deque(maxlen=200))
        self._event_number = defaultdict(int)
        self._final_messages = {}
        self._tool_turns = set()
        self.integration_verified = False

    async def start(self) -> None:
        async with self._start_lock:
            await self._start_locked()

    async def _start_locked(self) -> None:
        if self.process and self.process.returncode is None:
            return
        self._threads.clear()
        self._final_messages.clear()
        self._tool_turns.clear()
        self.integration_verified = False
        self._workspace = tempfile.TemporaryDirectory(prefix="quantflow-agent-")
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.executable, "app-server", "--stdio", stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace.name)
        except OSError as exc:
            self._workspace.cleanup()
            self._workspace = None
            raise AgentUnavailable("Codex App Server 不可启动") from exc
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        try:
            await self._rpc("initialize", {"clientInfo": {"name": "quantflow",
                  "title": "QuantFlow Research", "version": "0.1"},
                  "capabilities": {"experimentalApi": True, "requestAttestation": False}}, timeout=15)
            await self._write({"method": "initialized"})
        except Exception as exc:
            await self.close()
            raise AgentUnavailable("Codex App Server 握手失败") from exc

    async def _write(self, payload: Dict[str, Any]) -> None:
        if not self.process or self.process.returncode is not None or not self.process.stdin:
            raise AgentUnavailable("Codex App Server 已断开")
        async with self._write_lock:
            self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
            await self.process.stdin.drain()

    async def _rpc(self, method: str, params: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        self._next_id += 1
        call_id = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = future
        try:
            await self._write({"id": call_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(call_id, None)

    async def _read_stdout(self) -> None:
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "id" in message and "method" in message:
                    asyncio.create_task(self._handle_server_request(message))
                elif "id" in message:
                    future = self._pending.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(AgentUnavailable(str(message["error"].get("message", "RPC failed"))))
                        else:
                            future.set_result(message.get("result", {}))
                elif "method" in message:
                    self._record_notification(message)
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(AgentUnavailable("Codex App Server 已断开"))

    async def _drain_stderr(self) -> None:
        if self.process and self.process.stderr:
            while True:
                if not await self.process.stderr.read(4096):
                    return

    def _emit(self, thread_id: str, payload: Dict[str, Any]) -> None:
        if thread_id not in self._threads:
            return
        self._event_number[thread_id] += 1
        self._events[thread_id].append({"cursor": self._event_number[thread_id], **payload})

    def _record_notification(self, message: Dict[str, Any]) -> None:
        method = message.get("method")
        if method == "item/completed":
            params = message.get("params") or {}
            item = params.get("item") or {}
            if item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                self._final_messages[params.get("turnId")] = item.get("text", "")[:8000]
            return
        if method != "turn/completed":
            return
        params = message.get("params") or {}
        thread_id = params.get("threadId")
        if thread_id not in self._threads:
            return
        turn = params.get("turn") or {}
        items = turn.get("items") or []
        answers = [item.get("text", "") for item in items if item.get("type") == "agentMessage"]
        turn_id = turn.get("id")
        answer = (answers[-1] if answers else self._final_messages.get(turn_id, ""))[:8000]
        self._final_messages.pop(turn_id, None)
        try:
            self._audit_final(thread_id, turn_id, answer, turn.get("durationMs"))
        except Exception:
            answer = ""
            self._emit(thread_id, {"type": "audit_failed", "turn_id": turn_id})
        if turn.get("status") == "completed" and (thread_id, turn_id) in self._tool_turns and answer:
            self.integration_verified = True
        self._tool_turns.discard((thread_id, turn_id))
        self._emit(thread_id, {"type": "turn_completed", "turn_id": turn.get("id"),
                               "status": turn.get("status"),
                               "answer": answer})

    async def _handle_server_request(self, message: Dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params") or {}
        if method == "item/tool/call" and params.get("threadId") in self._threads:
            name = f"{params.get('namespace')}.{params.get('tool')}"
            started = time.perf_counter()
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict) or len(json.dumps(arguments)) > 10000:
                result = failure(name, "invalid_input", "工具输入格式或大小不符合要求")
                params["arguments"] = {}
            else:
                result = await asyncio.to_thread(invoke, name, arguments)
                if name not in TOOLS:
                    params["arguments"] = {}
            elapsed = round((time.perf_counter() - started) * 1000)
            try:
                self._audit_tool(params, name, result.model_dump(), elapsed)
            except Exception:
                result = failure(name, "audit_unavailable", "Agent 审计记录失败；工具结果已封锁")
            if result.success:
                self._tool_turns.add((params["threadId"], params.get("turnId")))
            self._emit(params["threadId"], {"type": "tool", "turn_id": params.get("turnId"),
                                            "tool": name, "success": result.success,
                                            "result": result.model_dump()})
            response = {"contentItems": [{"type": "inputText",
                         "text": result.model_dump_json()}], "success": result.success}
        elif method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            response = {"decision": "decline"}
        elif method == "mcpServer/elicitation/request":
            response = {"action": "decline", "content": None, "_meta": None}
        else:
            await self._write({"id": message["id"], "error": {
                "code": -32601, "message": "QuantFlow agent policy denies this request"}})
            return
        await self._write({"id": message["id"], "result": response})

    def _audit_tool(self, params: Dict[str, Any], name: str, result: Dict[str, Any], elapsed: int) -> None:
        initialize()
        with connect() as conn:
            conn.execute("""INSERT INTO agent_runs
              (run_id, thread_id, turn_id, skill, tools_called, tool_inputs,
               tool_outputs, approval_id, duration_ms, final_result, created_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
              (uuid.uuid4().hex, params["threadId"], params.get("turnId", ""), None,
               json.dumps([name]), json.dumps(params.get("arguments") or {}),
               json.dumps(result, ensure_ascii=False), None, elapsed, None))

    def _audit_final(self, thread_id: str, turn_id: str, answer: str, duration_ms: Any) -> None:
        initialize()
        with connect() as conn:
            conn.execute("""INSERT INTO agent_runs
              (run_id, thread_id, turn_id, skill, tools_called, tool_inputs,
               tool_outputs, approval_id, duration_ms, final_result, created_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
              (uuid.uuid4().hex, thread_id, turn_id, None, "[]", "{}", "{}",
               None, duration_ms, answer))

    async def create_thread(self) -> str:
        overrides = {**{f"features.{key}": value for key, value in _DISABLED_FEATURES.items()},
                     **_disabled_mcp_servers()}
        await self.start()
        response = await self._rpc("thread/start", {
            "cwd": self._workspace.name, "sandbox": "read-only",
            "approvalPolicy": "never", "baseInstructions": _INSTRUCTIONS,
            "ephemeral": True,
            "config": overrides,
            "dynamicTools": tool_specs()})
        thread_id = response.get("thread", {}).get("id")
        if not thread_id:
            raise AgentUnavailable("Codex 未返回 thread id")
        self._threads.add(thread_id)
        return thread_id

    async def run_turn(self, thread_id: str, prompt: str, context: Dict[str, Any], skill: str) -> str:
        if thread_id not in self._threads:
            raise AgentUnavailable("会话不存在或已失效")
        if skill not in _RESEARCH_SKILLS:
            raise AgentUnavailable("该技能不属于只读研究 runtime")
        skill_path = _SKILL_ROOT / skill / "SKILL.md"
        if not skill_path.is_file():
            raise AgentUnavailable("研究技能文件不可用")
        content = f"页面上下文（未经验证，仅作定位）：{json.dumps(context, ensure_ascii=False)}\n用户问题：{prompt}"
        response = await self._rpc("turn/start", {"threadId": thread_id,
            "input": [{"type": "skill", "name": skill, "path": str(skill_path)},
                      {"type": "text", "text": content, "text_elements": []}]})
        turn_id = response.get("turn", {}).get("id")
        if not turn_id:
            raise AgentUnavailable("Codex 未返回 turn id")
        return turn_id

    def events(self, thread_id: str, after: int = 0) -> List[Dict[str, Any]]:
        if thread_id not in self._threads:
            raise AgentUnavailable("会话不存在或已失效")
        return [event for event in self._events[thread_id] if event["cursor"] > after][:100]

    async def cancel(self, thread_id: str, turn_id: str) -> None:
        if thread_id not in self._threads:
            raise AgentUnavailable("会话不存在或已失效")
        await self._rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})

    async def approve(self, approval_id: str) -> None:
        raise AgentUnavailable("Agent 不具备审批权限；须由可信人工流程处理")

    async def close(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._reader_task:
            await asyncio.gather(self._reader_task, return_exceptions=True)
        if self._stderr_task:
            await asyncio.gather(self._stderr_task, return_exceptions=True)
        if self._workspace:
            self._workspace.cleanup()
        self._threads.clear()
