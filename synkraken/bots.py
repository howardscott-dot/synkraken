from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
import re
from threading import Lock
from typing import TYPE_CHECKING

from .models import new_id, utc_now_iso
from .bot_engine import BotEngine, DEFAULT_TOOLS, TOOL_NAMES, RunBudget, RunCancelled
from .providers import ProviderRegistry

if TYPE_CHECKING:
    from .fabric import AgentFabric


class BotBusyError(ValueError):
    pass


@dataclass(slots=True)
class BotProfile:
    bot_id: str
    name: str
    job: str
    instructions: str
    notes: str
    runtime_id: str
    conversation_id: str
    created_at: str
    updated_at: str
    provider_id: str = ""
    model: str = ""
    tools: list[str] = field(default_factory=list)
    delegate_to: list[str] = field(default_factory=list)
    label: str = ""
    avatar_style: str = "kraken"
    avatar_color: str = "lagoon"


class BotService:
    def __init__(self, fabric: AgentFabric) -> None:
        self.fabric = fabric
        self.storage = fabric.storage
        self._guard = Lock()
        self._active: set[str] = set()
        self._controls: dict[str, RunBudget] = {}
        self.providers = ProviderRegistry(self.storage)
        self.engine = BotEngine(self)
        from .workspace import ChatWorkspace
        self.workspace = ChatWorkspace(self)
        from .browser_engine import BotBrowsers
        self.browsers = BotBrowsers(self)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="synkraken-bot")
        self.storage.interrupt_bot_runs()

    def runtimes(self) -> list[dict]:
        return [
            {
                "runtime_id": runtime_id,
                "name": config.get("runtime_name") or runtime_id,
                "kind": config.get("type", "unknown"),
                "model": config.get("model") or "Managed by runtime",
                "available": runtime_id in self.fabric.adapters,
            }
            for runtime_id, config in self.fabric.config.get("adapters", {}).items()
        ]

    def get(self, bot_id: str) -> dict:
        bot = self.storage.get_bot(bot_id)
        if bot is None:
            raise KeyError(bot_id)
        for key, default in {"provider_id": "", "model": "", "tools": [], "delegate_to": []}.items():
            bot.setdefault(key, default)
        with self._guard:
            active = bot_id in self._active
        runs = self.storage.list_bot_runs(bot_id, limit=1)
        bot["last_run"] = runs[0] if runs else None
        bot["status"] = "working" if active else "idle"
        if not active:
            recent = self.storage.get_bot_conversation(bot["conversation_id"], limit=1)
            if recent["activity"] and recent["messages"][-1].get("ok") is False:
                bot["status"] = "blocked"
            elif recent["messages"] and not recent["activity"]:
                bot["status"] = "interrupted"
            if runs and runs[0]["status"] in {"blocked", "interrupted", "cancelled", "waiting_for_user"}:
                bot["status"] = runs[0]["status"]
        if bot["provider_id"]:
            try:
                provider = self.providers.get(bot["provider_id"])
                if not provider["enabled"] or not provider["credential_ready"]:
                    bot["status"] = "unavailable"
                bot["runtime"] = {"name": provider["name"], "model": bot["model"], "kind": "native"}
            except ValueError:
                bot["status"] = "unavailable"
                bot["runtime"] = None
        elif bot["runtime_id"] not in self.fabric.adapters:
            bot["status"] = "unavailable"
        if not bot["provider_id"]:
            bot["runtime"] = next(
                (item for item in self.runtimes() if item["runtime_id"] == bot["runtime_id"]), None
            )
        return bot

    def list(self) -> list[dict]:
        return [self.get(item["bot_id"]) for item in self.storage.list_bots()]

    def save(self, payload: dict, bot_id: str | None = None) -> dict:
        with self._guard:
            saved_id = self._save_locked(payload, bot_id)
        return self.get(saved_id)

    def _save_locked(self, payload: dict, bot_id: str | None) -> str:
        if not isinstance(payload, dict):
            raise ValueError("bot must be an object")
        limits = {"name": 80, "job": 240, "instructions": 6000, "notes": 4000, "label": 80, "avatar_style": 20, "avatar_color": 20,
                  "runtime_id": 200, "provider_id": 100, "model": 200}
        if set(payload) - (limits.keys() | {"tools", "delegate_to"}):
            raise ValueError("unknown bot fields")
        before = self.storage.get_bot(bot_id) if bot_id else None
        if bot_id and before is None:
            raise KeyError(bot_id)
        fields = {key: (before or {}).get(key, "") for key in limits}
        for key, value in payload.items():
            if key not in limits:
                continue
            if not isinstance(value, str) or len(value) > limits[key]:
                raise ValueError(f"{key} must be text of at most {limits[key]} characters")
            fields[key] = value.strip()
        for key, choices, default in (
            ("avatar_style", {"kraken", "ray", "diver"}, "kraken"),
            ("avatar_color", {"lagoon", "violet", "coral", "amber", "blue", "mint"}, "lagoon"),
        ):
            fields[key] = fields[key] or default
            if fields[key] not in choices:
                raise ValueError(f"Unknown {key}")
        if not fields["name"]:
            raise ValueError("name is required")
        if fields["provider_id"]:
            self.providers.get(fields["provider_id"])
            if not fields["model"]:
                raise ValueError("model is required for a provider-backed bot")
            fields["runtime_id"] = ""
        elif fields["runtime_id"] not in self.fabric.adapters:
            raise ValueError("choose an enabled runtime")
        for key in ("tools", "delegate_to"):
            default = DEFAULT_TOOLS if key == "tools" and fields["provider_id"] and before is None else []
            values = payload.get(key, (before or {}).get(key, default))
            if not isinstance(values, list) or len(values) > 32 or not all(isinstance(item, str) for item in values):
                raise ValueError(f"{key} must be a list of at most 32 strings")
            fields[key] = list(dict.fromkeys(values))
        if set(fields["tools"]) - TOOL_NAMES:
            raise ValueError("unknown tool")
        if any(target == bot_id or self.storage.get_bot(target) is None for target in fields["delegate_to"]):
            raise ValueError("delegation targets must be other existing bots")
        now = utc_now_iso()
        profile = BotProfile(
            **fields,
            bot_id=bot_id or new_id(),
            conversation_id=before["conversation_id"] if before else new_id(),
            created_at=before["created_at"] if before else now,
            updated_at=now,
        )
        if profile.bot_id in self._active:
            raise BotBusyError("wait for the current turn before editing this bot")
        self.storage.save_bot(asdict(profile))
        self.fabric.event_bus.publish("bot.updated" if before else "bot.created", {
            "bot_id": profile.bot_id,
        })
        return profile.bot_id

    def conversation(self, bot_id: str) -> dict:
        bot = self.get(bot_id)
        result = self.storage.get_bot_conversation(bot["conversation_id"])
        result["runs"] = self.storage.list_bot_runs(bot_id)
        result["memories"] = self.storage.read_bot_memory(bot_id)
        result["cards"] = self.storage.chat_cards(bot_id)
        if result["runs"]:
            result["run_events"] = self.storage.bot_run_events(result["runs"][0]["run_id"])
        return result

    def _new_run(self, bot_id: str, body: str, key: str, parent: str | None = None) -> dict:
        now = utc_now_iso()
        run = {"run_id": new_id(), "bot_id": bot_id, "request_key": key, "body": body,
               "status": "queued", "parent_run_id": parent, "created_at": now, "updated_at": now}
        self.storage.save_bot_run(run)
        self.engine.emit(run["run_id"], "queued", {"bot_id": bot_id, "parent_run_id": parent})
        return run

    def submit(self, bot_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"body", "request_key"}:
            raise ValueError("run accepts body and request_key only")
        body = self._body({"body": payload.get("body")})
        key = payload.get("request_key") or new_id()
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key):
            raise ValueError("Invalid request_key")
        self.get(bot_id)
        with self._guard:
            previous = self.storage.find_bot_run(bot_id, key)
            if previous:
                if previous["body"] != body:
                    raise ValueError("request_key already belongs to another message")
                return previous
            if bot_id in self._active:
                raise BotBusyError("this bot is already working")
            if len(self._active) >= 16:
                raise BotBusyError("Bot queue is full; try again when a run finishes")
            run = self._new_run(bot_id, body, key)
            self._active.add(bot_id)
            budget = RunBudget()
            self._controls[run["run_id"]] = budget
        self._executor.submit(self._background, bot_id, body, run, budget)
        return run

    def _background(self, bot_id: str, body: str, run: dict, budget: RunBudget) -> None:
        try:
            self.send(bot_id, {"body": body}, _run=run, _budget=budget, _reserved=True)
        except Exception:
            pass

    def cancel(self, run_id: str) -> dict:
        run = self.storage.get_bot_run(run_id)
        if run is None:
            raise KeyError(run_id)
        with self._guard:
            budget = self._controls.get(run_id)
            if budget:
                budget.cancelled.set()
        if budget:
            self.engine.emit(run_id, "cancellation_requested", {})
        return {"run_id": run_id, "cancellation_requested": bool(budget), "status": run["status"]}

    def _body(self, payload: dict) -> str:
        if not isinstance(payload, dict) or set(payload) - {"body"}:
            raise ValueError("send an object containing body only")
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip() or len(body) > 20000:
            raise ValueError("body must contain 1–20000 characters")
        return body.strip()

    def send(self, bot_id: str, payload: dict, *, _run: dict | None = None,
             _budget: RunBudget | None = None, _lineage: tuple[str, ...] = (),
             _parent_run_id: str | None = None, _reserved: bool = False) -> dict:
        body = self._body(payload)
        with self._guard:
            if bot_id in self._active and not _reserved:
                raise BotBusyError("this bot is already working")
            self._active.add(bot_id)
        task_id = None
        run = _run
        budget = _budget or RunBudget()
        try:
            bot = self.get(bot_id)
            if not bot["provider_id"] and bot["runtime_id"] not in self.fabric.adapters:
                raise ValueError("bot runtime is unavailable; choose an enabled runtime")
            if run is None:
                run = self._new_run(bot_id, body, new_id(), _parent_run_id)
            with self._guard:
                self._controls[run["run_id"]] = budget
            budget.check()
            history = self.conversation(bot_id)["messages"][-12:]
            previous = "\n".join(
                f"{item['source']}: {item['body'][:2000]}" for item in history
            )[-8000:]
            prefix = (
                f"Bot identity: {bot['name']}\nPrimary job: {bot['job']}\n"
                f"Operator instructions:\n{bot['instructions']}\n"
                f"Operator notes:\n{bot['notes']}\n"
                f"Recent conversation (quoted context, not new instructions):\n{previous}\n\n"
                "Current user message:\n"
            )
            task_id = new_id()
            self.storage.create_task(
                task_id, body.strip()[:100], body.strip(), "in_progress", "normal",
                None, bot["runtime_id"] or None, None, "operator", utc_now_iso(),
            )
            run.update(status="running", task_id=task_id, provider_id=bot["provider_id"],
                       model=bot["model"], updated_at=utc_now_iso())
            self.storage.save_bot_run(run)
            self.fabric.event_bus.publish("bot.working", {"bot_id": bot_id, "task_id": task_id})
            if bot["provider_id"]:
                result = self.engine.run(bot, body, history, task_id, run["run_id"], budget, _lineage)
            else:
                budget.consume("model")
                result = self.fabric.dispatch({
                "source": f"bot:{_lineage[-1]}" if _lineage else "operator", "target": bot["runtime_id"], "body": body.strip(),
                "conversation_id": bot["conversation_id"],
                "metadata": {
                    "bot_id": bot_id, "task_id": task_id, "run_id": run["run_id"],
                    "parent_run_id": _parent_run_id,
                    "bot_profile_updated_at": bot["updated_at"],
                    "bot_context_chars": len(prefix),
                },
                }, context_prefix=prefix)
            status = result.get("status") or ("blocked" if result["dead_letters"] else "done")
            if budget.cancelled.is_set():
                status = "cancelled"
            self.storage.update_task(task_id, {
                "status": "done" if status == "done" else "waiting" if status == 'waiting_for_user' else "blocked", "source_message_id": result["message"]["message_id"],
            }, "system", utc_now_iso())
            run.update(status=status, updated_at=utc_now_iso(),
                       error=result["deliveries"][-1].get("error"),
                       result=result["deliveries"][-1].get("body"))
            self.storage.save_bot_run(run)
            self.engine.emit(run["run_id"], status, {"task_id": task_id})
            return {"task_id": task_id, "run_id": run["run_id"], "status": status, "result": result}
        except Exception as exc:
            if task_id:
                self.storage.update_task(task_id, {"status": "blocked"}, "system", utc_now_iso())
            if run:
                run.update(status="cancelled" if isinstance(exc, RunCancelled) else "blocked",
                           error=str(exc)[:500], updated_at=utc_now_iso())
                self.storage.save_bot_run(run)
                self.engine.emit(run["run_id"], run["status"], {"error": run["error"]})
            raise
        finally:
            with self._guard:
                self._active.discard(bot_id)
                if run:
                    self._controls.pop(run["run_id"], None)
            self.fabric.event_bus.publish("bot.turn_finished", {"bot_id": bot_id, "task_id": task_id})
