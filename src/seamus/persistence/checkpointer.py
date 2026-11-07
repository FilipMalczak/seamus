"""LangGraph checkpointer that serializes checkpoints to disk and commits to Git."""

import base64
import logging
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import MemorySaver

from seamus.domain.entities import Session
from seamus.domain.resolution import parse_uuid
from seamus.persistence.workspace import GitWorkspaceManager, get_workspace_manager
from seamus.vault.interpolator import explode_secret_references

logger = logging.getLogger(__name__)


def extract_readable_messages(checkpoint: Checkpoint) -> list[dict[str, Any]]:
    """Extract a human-readable list of messages from checkpoint channel values."""
    values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    raw_msgs = values.get("messages", []) if isinstance(values, dict) else []
    result: list[dict[str, Any]] = []
    for msg in raw_msgs:
        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type") or "unknown"
            content = msg.get("content", "")
            id_val = msg.get("id")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id")
        else:
            role = getattr(msg, "type", None) or getattr(msg, "role", "unknown")
            content = getattr(msg, "content", "")
            id_val = getattr(msg, "id", None)
            tool_calls = getattr(msg, "tool_calls", None)
            tool_call_id = getattr(msg, "tool_call_id", None)

        item: dict[str, Any] = {
            "id": id_val,
            "role": role,
            "content": content,
        }
        if tool_calls:
            item["tool_calls"] = tool_calls
        if tool_call_id:
            item["tool_call_id"] = tool_call_id
        result.append(item)
    return result


def extract_readable_todos(checkpoint: Checkpoint) -> list[dict[str, Any]]:
    """Extract a list of todo items from checkpoint channel values."""
    values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    raw_todos = values.get("todos", []) if isinstance(values, dict) else []
    result: list[dict[str, Any]] = []
    if isinstance(raw_todos, list):
        for item in raw_todos:
            if isinstance(item, dict):
                content = str(item.get("content", ""))
                status = str(item.get("status", "pending"))
                result.append({"content": content, "status": status})
    return result


class GitCheckpointSaver(MemorySaver):
    """Checkpointer that persists checkpoint state to disk and commits changes to Git."""

    def __init__(
        self,
        agent_id: UUID,
        session_id: UUID,
        workspace_manager: GitWorkspaceManager | None = None,
        inner: BaseCheckpointSaver[Any] | None = None,
        session: Session | None = None,
        secret_versions_provider: Callable[[], Mapping[tuple[str, str], int]] | None = None,
    ) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.session_id = session_id
        self.workspace_manager = workspace_manager or get_workspace_manager()
        self.inner = inner
        self.session = session
        self.secret_versions_provider = secret_versions_provider
        self._load_from_workspace()

    def copy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        """Copy all checkpoints, writes, and blobs from one thread to another."""
        src_keys = [source_thread_id]
        tgt_keys = [target_thread_id]
        src_uuid = parse_uuid(source_thread_id)
        if src_uuid:
            src_keys.extend([src_uuid.hex, str(src_uuid)])
        tgt_uuid = parse_uuid(target_thread_id)
        if tgt_uuid:
            tgt_keys.extend([tgt_uuid.hex, str(tgt_uuid)])

        found_src = None
        for k in src_keys:
            if k in self.storage:
                found_src = k
                break

        if found_src:
            for tgt in tgt_keys:
                self.storage[tgt] = {ns: dict(cps) for ns, cps in self.storage[found_src].items()}

        for (t_id, ns, cp_id), w_dict in list(self.writes.items()):
            if t_id in src_keys:
                for tgt in tgt_keys:
                    self.writes[(tgt, ns, cp_id)] = dict(w_dict)

        for (t_id, ns, ch, ver), blob in list(self.blobs.items()):
            if t_id in src_keys:
                for tgt in tgt_keys:
                    self.blobs[(tgt, ns, ch, ver)] = blob

        if tgt_uuid:
            try:
                dump = self.dump_state(target_uuid=tgt_uuid)
                self.workspace_manager.save_thread_checkpoints(
                    self.agent_id, self.session_id, tgt_uuid, dump
                )
            except Exception:
                logger.exception("Failed to save copied checkpoints to disk for %s", tgt_uuid)

    def dump_state(self, target_uuid: UUID | None = None) -> dict[str, Any]:
        """Serialize internal storage, writes, and blobs to a JSON-compatible dict."""
        storage_dump: dict[str, Any] = {}
        for t_id, ns_dict in self.storage.items():
            t_uuid = parse_uuid(t_id)
            if target_uuid and t_uuid != target_uuid and t_id != str(target_uuid):
                continue
            storage_dump[t_id] = {}
            for ns, cp_dict in ns_dict.items():
                storage_dump[t_id][ns] = {}
                for cp_id, (cp_tb, meta_tb, parent_id) in cp_dict.items():
                    storage_dump[t_id][ns][cp_id] = [
                        [cp_tb[0], base64.b64encode(cp_tb[1]).decode("ascii")],
                        [meta_tb[0], base64.b64encode(meta_tb[1]).decode("ascii")],
                        parent_id,
                    ]

        writes_dump: list[dict[str, Any]] = []
        for (t_id, ns, cp_id), w_dict in self.writes.items():
            t_uuid = parse_uuid(t_id)
            if target_uuid and t_uuid != target_uuid and t_id != str(target_uuid):
                continue
            for (task_id, idx), (_tid, ch, val_tb, path) in w_dict.items():
                writes_dump.append(
                    {
                        "thread_id": t_id,
                        "checkpoint_ns": ns,
                        "checkpoint_id": cp_id,
                        "task_id": task_id,
                        "idx": idx,
                        "channel": ch,
                        "val_type": val_tb[0],
                        "val_blob": base64.b64encode(val_tb[1]).decode("ascii"),
                        "task_path": path,
                    }
                )

        blobs_dump: list[dict[str, Any]] = []
        for (t_id, ns, ch, ver), b_tb in self.blobs.items():
            t_uuid = parse_uuid(t_id)
            if target_uuid and t_uuid != target_uuid and t_id != str(target_uuid):
                continue
            blobs_dump.append(
                {
                    "thread_id": t_id,
                    "checkpoint_ns": ns,
                    "channel": ch,
                    "version": ver,
                    "blob_type": b_tb[0],
                    "blob_data": base64.b64encode(b_tb[1]).decode("ascii"),
                }
            )

        return {
            "storage": storage_dump,
            "writes": writes_dump,
            "blobs": blobs_dump,
        }

    def load_state(self, data: dict[str, Any]) -> None:
        """Deserialize JSON-compatible dict into internal storage, writes, and blobs."""
        for t_id, ns_dict in data.get("storage", {}).items():
            for ns, cp_dict in ns_dict.items():
                for cp_id, (cp_data, meta_data, parent_id) in cp_dict.items():
                    self.storage[t_id][ns][cp_id] = (
                        (cp_data[0], base64.b64decode(cp_data[1])),
                        (meta_data[0], base64.b64decode(meta_data[1])),
                        parent_id,
                    )

        for w in data.get("writes", []):
            writes_key = (str(w["thread_id"]), str(w["checkpoint_ns"]), str(w["checkpoint_id"]))
            self.writes[writes_key][(str(w["task_id"]), int(w["idx"]))] = (
                str(w["task_id"]),
                str(w["channel"]),
                (str(w["val_type"]), base64.b64decode(w["val_blob"])),
                str(w["task_path"]),
            )

        for b in data.get("blobs", []):
            blob_key = (
                str(b["thread_id"]),
                str(b["checkpoint_ns"]),
                str(b["channel"]),
                b["version"],
            )
            self.blobs[blob_key] = (str(b["blob_type"]), base64.b64decode(b["blob_data"]))

    def _load_from_workspace(self) -> None:
        """Load any persisted thread checkpoints from the session workspace."""
        try:
            checkpoint_dumps = self.workspace_manager.load_all_thread_checkpoints(
                self.agent_id, self.session_id
            )
            for dump in checkpoint_dumps:
                self.load_state(dump)
            if checkpoint_dumps:
                logger.info(
                    "Restored %d thread checkpoints from workspace for session %s",
                    len(checkpoint_dumps),
                    self.session_id,
                )
        except Exception:
            logger.exception(
                "Error restoring checkpoints from workspace for agent %s session %s",
                self.agent_id,
                self.session_id,
            )

    def _save_checkpoint_to_disk(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
    ) -> None:
        """Save checkpoint data and human-readable messages to disk."""
        try:
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            thread_raw = configurable.get("thread_id")
            thread_uuid = parse_uuid(thread_raw) if thread_raw else self.session_id
            target_uuid = thread_uuid or self.session_id

            dump = self.dump_state(target_uuid=target_uuid)
            self.workspace_manager.save_thread_checkpoints(
                self.agent_id, self.session_id, target_uuid, dump
            )

            messages = extract_readable_messages(checkpoint)
            if messages:
                self.workspace_manager.save_thread_messages(
                    self.agent_id, self.session_id, target_uuid, messages
                )

            todos = extract_readable_todos(checkpoint)
            if todos:
                self.workspace_manager.save_thread_todos(
                    self.agent_id, self.session_id, target_uuid, todos
                )

            if self.session is not None:
                version_map = (
                    self.secret_versions_provider()
                    if self.secret_versions_provider is not None
                    else {}
                )
                exploded_cfg = explode_secret_references(
                    self.session.config.model_dump(),
                    version_map,
                )
                self.workspace_manager.write_session_config_file(
                    self.session,
                    config_dict=exploded_cfg,
                )
        except Exception:
            logger.exception("Failed to save checkpoint to disk for session %s", self.session_id)

    def _trigger_git_commit(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
    ) -> None:
        try:
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            thread_raw = configurable.get("thread_id")
            thread_uuid = parse_uuid(thread_raw) if thread_raw else self.session_id
            cp_id = checkpoint.get("id") if isinstance(checkpoint, dict) else None

            self.workspace_manager.commit_checkpoint_changes(
                agent_id=self.agent_id,
                session_id=self.session_id,
                thread_id=thread_uuid or self.session_id,
                checkpoint_id=str(cp_id) if cp_id else None,
            )
        except Exception:
            logger.exception(
                "Error committing checkpoint changes for agent %s session %s",
                self.agent_id,
                self.session_id,
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        res = (
            self.inner.put(config, checkpoint, metadata, new_versions)
            if self.inner is not None
            else super().put(config, checkpoint, metadata, new_versions)
        )
        self._save_checkpoint_to_disk(config, checkpoint)
        self._trigger_git_commit(config, checkpoint)
        return res

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        if self.inner is not None:
            res = await self.inner.aput(config, checkpoint, metadata, new_versions)
            self._save_checkpoint_to_disk(config, checkpoint)
            self._trigger_git_commit(config, checkpoint)
            return res
        return await super().aput(config, checkpoint, metadata, new_versions)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        if self.inner is not None:
            return self.inner.get_tuple(config)
        return super().get_tuple(config)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        if self.inner is not None:
            return await self.inner.aget_tuple(config)
        return await super().aget_tuple(config)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if self.inner is not None:
            return self.inner.list(config, filter=filter, before=before, limit=limit)
        return super().list(config, filter=filter, before=before, limit=limit)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if self.inner is not None:
            async for item in self.inner.alist(config, filter=filter, before=before, limit=limit):
                yield item
        else:
            async for item in super().alist(config, filter=filter, before=before, limit=limit):
                yield item

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        if self.inner is not None:
            self.inner.put_writes(config, writes, task_id, task_path=task_path)
        else:
            super().put_writes(config, writes, task_id, task_path=task_path)
        try:
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            thread_raw = configurable.get("thread_id")
            thread_uuid = parse_uuid(thread_raw) if thread_raw else self.session_id
            target_uuid = thread_uuid or self.session_id
            dump = self.dump_state(target_uuid=target_uuid)
            self.workspace_manager.save_thread_checkpoints(
                self.agent_id, self.session_id, target_uuid, dump
            )
        except Exception:
            logger.exception("Failed to save writes to disk for session %s", self.session_id)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        if self.inner is not None:
            await self.inner.aput_writes(config, writes, task_id, task_path=task_path)
        else:
            await super().aput_writes(config, writes, task_id, task_path=task_path)
        try:
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            thread_raw = configurable.get("thread_id")
            thread_uuid = parse_uuid(thread_raw) if thread_raw else self.session_id
            target_uuid = thread_uuid or self.session_id
            dump = self.dump_state(target_uuid=target_uuid)
            self.workspace_manager.save_thread_checkpoints(
                self.agent_id, self.session_id, target_uuid, dump
            )
        except Exception:
            logger.exception("Failed to save async writes to disk for session %s", self.session_id)
