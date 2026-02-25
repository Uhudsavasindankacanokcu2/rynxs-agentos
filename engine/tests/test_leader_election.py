"""
Leader election behavior tests.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

from engine.core.events import Event
from engine.log.file_store import FileEventStore


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = REPO_ROOT / "operator" / "universe_operator" / "main.py"


def _install_dummy_k8s_modules():
    k8s = types.ModuleType("kubernetes")
    k8s.config = types.SimpleNamespace(load_incluster_config=lambda: None)

    client_mod = types.ModuleType("kubernetes.client")
    rest_mod = types.ModuleType("kubernetes.client.rest")

    class ApiException(Exception):
        def __init__(self, status: int = 0):
            super().__init__("api exception")
            self.status = status

    rest_mod.ApiException = ApiException

    class DummyApi:
        def __init__(self, *args, **kwargs):
            pass

    class DummyObj:
        def __init__(self, *args, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    client_mod.CoreV1Api = DummyApi
    client_mod.AppsV1Api = DummyApi
    client_mod.NetworkingV1Api = DummyApi
    client_mod.CoordinationV1Api = DummyApi
    client_mod.V1LeaseSpec = DummyObj
    client_mod.V1Lease = DummyObj
    client_mod.V1ObjectMeta = DummyObj

    k8s.client = client_mod

    sys.modules["kubernetes"] = k8s
    sys.modules["kubernetes.client"] = client_mod
    sys.modules["kubernetes.client.rest"] = rest_mod


def _install_dummy_kopf_module():
    kopf = types.ModuleType("kopf")

    class DummyOn:
        def startup(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

        def create(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

        def update(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

    kopf.on = DummyOn()
    kopf.OperatorSettings = type("OperatorSettings", (), {})

    sys.modules["kopf"] = kopf


def _load_main_module(env: dict) -> types.ModuleType:
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    _install_dummy_k8s_modules()
    _install_dummy_kopf_module()

    spec = importlib.util.spec_from_file_location("rynxs_main_test", str(MAIN_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def test_leader_election_follower_skips_side_effects():
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "EVENT_STORE_PATH": str(Path(tmpdir) / "test.log"),
            "RYNXS_LEADER_ELECTION_ENABLED": "1",
            "RYNXS_WRITER_ID": "ci",
        }
        main = _load_main_module(env)

        class StubLeader:
            def is_enabled(self):
                return True

            def is_leader(self):
                return False

        class StubStore:
            def __init__(self):
                self.append_calls = 0

            def append_with_retry(self, *args, **kwargs):
                self.append_calls += 1
                raise AssertionError("append_with_retry called in follower mode")

            def get_event_hash(self, *args, **kwargs):
                return None

        class StubExecutor:
            def __init__(self, *args, **kwargs):
                pass

            def apply(self, actions):
                raise AssertionError("executor.apply called in follower mode")

        main.leader_elector = StubLeader()
        main.event_store = StubStore()
        main.ExecutorLayer = StubExecutor

        logger = _Logger()
        main.agent_reconcile(
            spec={"role": "worker"},
            name="agent-001",
            namespace="universe",
            logger=logger,
            meta={"labels": {}},
        )
        assert main.event_store.append_calls == 0


def test_writer_id_meta_committed_when_env_set():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = str(Path(tmpdir) / "test.log")
        env = {
            "EVENT_STORE_PATH": log_path,
            "RYNXS_WRITER_ID": "ci",
        }
        main = _load_main_module(env)

        event = Event(type="TEST", aggregate_id="A", ts=1)
        with_writer = main._with_writer_id(event)
        assert with_writer.meta.get("writer_id") == "ci"

        store = FileEventStore(log_path)
        result = store.append(with_writer)
        assert result.event.meta.get("writer_id") == "ci"
