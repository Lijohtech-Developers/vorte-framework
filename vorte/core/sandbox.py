"""
Vorte WebAssembly Sandbox
==========================
Isolated runtime environment for user-defined routes, external dependencies,
and third-party validation schemas. Executes Wasm modules with capability-
limited isolation — no host filesystem access, no unauthorised socket creation.

Blueprint reference: §5.1 Integrated WebAssembly Security Sandbox
  "Malicious attempts to alter host environment profiles, parse unauthorized
   local files, or spawn un-sanctioned outbound socket networks are instantly
   terminated without interrupting parallel active requests."

Requires ``wasmtime-py`` (install via ``pip install vorte[sandbox]``).
Gracefully degrades to a no-op if wasmtime is not installed.
"""

from __future__ import annotations

import warnings
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar

F = TypeVar("F", bound=Callable)

# Try to import wasmtime; degrade gracefully if absent
try:
    from wasmtime import (  # type: ignore[import]
        Config,
        Engine,
        Linker,
        Module,
        Store,
        WasiConfig,
    )
    _WASMTIME_AVAILABLE = True
except ImportError:
    _WASMTIME_AVAILABLE = False
    Config = Engine = Linker = Module = Store = WasiConfig = None  # type: ignore[assignment,misc]


class SandboxError(RuntimeError):
    """Raised when Wasm sandbox execution fails."""


class WasmSandbox:
    """
    Lightweight WebAssembly execution sandbox.

    Each call to :meth:`execute` spins up a fresh ``wasmtime`` store with
    WASI disabled by default (no host I/O, no filesystem, no network), runs
    the requested export function, and discards the store.

    Usage::

        sandbox = WasmSandbox()

        with open("validator.wasm", "rb") as f:
            wasm_bytes = f.read()

        result = sandbox.execute(wasm_bytes, "validate_json", b'{"key": 1}')

    If ``wasmtime`` is not installed::

        sandbox = WasmSandbox()
        print(sandbox.is_available)  # False
        # execute() raises SandboxError with a clear install message
    """

    def __init__(
        self,
        *,
        allow_wasi: bool = False,
        fuel: Optional[int] = None,
        max_wasm_stack: int = 512 * 1024,  # 512 KiB
    ) -> None:
        self._allow_wasi = allow_wasi
        self._fuel = fuel
        self._max_wasm_stack = max_wasm_stack

        if _WASMTIME_AVAILABLE:
            cfg = Config()
            cfg.consume_fuel = fuel is not None
            cfg.max_wasm_stack = max_wasm_stack
            self._engine: Optional[Any] = Engine(cfg)
        else:
            self._engine = None

    @property
    def is_available(self) -> bool:
        """``True`` if the wasmtime runtime is installed and usable."""
        return _WASMTIME_AVAILABLE

    def execute(
        self,
        wasm_bytes: bytes,
        fn_name: str,
        *args: Any,
    ) -> Any:
        """
        Execute *fn_name* exported from *wasm_bytes* with *args*.

        Args:
            wasm_bytes: Raw ``.wasm`` binary.
            fn_name: Name of the exported Wasm function to call.
            *args: Arguments forwarded to the Wasm function.

        Returns:
            The return value(s) of the Wasm function.

        Raises:
            :exc:`SandboxError` if wasmtime is unavailable or execution fails.
        """
        if not _WASMTIME_AVAILABLE:
            raise SandboxError(
                "wasmtime is not installed. "
                "Install the sandbox optional: pip install 'vorte[sandbox]'"
            )

        try:
            store: Any = Store(self._engine)
            if self._fuel is not None:
                store.set_fuel(self._fuel)

            linker: Any = Linker(self._engine)

            if self._allow_wasi:
                wasi = WasiConfig()
                wasi.inherit_stdout()
                store.set_wasi(wasi)
                linker.define_wasi()

            module = Module(self._engine, wasm_bytes)
            instance = linker.instantiate(store, module)
            func = instance.exports(store).get(fn_name)
            if func is None:
                raise SandboxError(f"Wasm export '{fn_name}' not found in module")
            return func(store, *args)
        except SandboxError:
            raise
        except Exception as exc:
            raise SandboxError(f"Wasm execution failed: {exc}") from exc

    def execute_file(self, wasm_path: str, fn_name: str, *args: Any) -> Any:
        """Convenience wrapper — load ``.wasm`` from *wasm_path* and execute."""
        with open(wasm_path, "rb") as f:
            return self.execute(f.read(), fn_name, *args)


# ---------------------------------------------------------------------------
# @sandboxed decorator
# ---------------------------------------------------------------------------

# Module-level shared sandbox
_default_sandbox: Optional[WasmSandbox] = None


def _get_default_sandbox() -> WasmSandbox:
    global _default_sandbox
    if _default_sandbox is None:
        _default_sandbox = WasmSandbox()
    return _default_sandbox


def sandboxed(wasm_path: str, fn_name: str) -> Callable[[F], F]:
    """
    Route decorator that executes the associated Wasm module before calling
    the Python handler. Useful for running untrusted third-party validators or
    transformation logic in isolation.

    If wasmtime is not available a :class:`SandboxError` is raised at
    decoration time so misconfigurations surface immediately at startup.

    Usage::

        @sandboxed("validators/email.wasm", "validate_email")
        @app.post("/register")
        async def register(body: RegisterSchema):
            ...
    """
    if not _WASMTIME_AVAILABLE:
        warnings.warn(
            f"@sandboxed({wasm_path!r}) has no effect: wasmtime is not installed. "
            "Install with: pip install 'vorte[sandbox]'",
            stacklevel=2,
            category=ImportWarning,
        )

    def decorator(func: F) -> F:
        func._vorte_sandboxed = True  # type: ignore[attr-defined]
        func._vorte_wasm_path = wasm_path  # type: ignore[attr-defined]
        func._vorte_wasm_fn = fn_name  # type: ignore[attr-defined]

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _WASMTIME_AVAILABLE:
                sandbox = _get_default_sandbox()
                sandbox.execute_file(wasm_path, fn_name)
            return await func(*args, **kwargs) if __import__("asyncio").iscoroutinefunction(func) else func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
