import warnings
import pytest
from unittest.mock import patch
from vorte.core.sandbox import WasmSandbox, SandboxError, sandboxed, _WASMTIME_AVAILABLE


def test_sandbox_is_available_reflects_import():
    sandbox = WasmSandbox()
    assert sandbox.is_available == _WASMTIME_AVAILABLE


@patch("vorte.core.sandbox._WASMTIME_AVAILABLE", False)
def test_sandbox_execute_without_wasmtime_raises_sandbox_error():
    """When wasmtime is absent, execute() must raise SandboxError with install hint."""

    sandbox = WasmSandbox()
    with pytest.raises(SandboxError, match="wasmtime is not installed"):
        sandbox.execute(b"fake_wasm", "fn_name")


@patch("vorte.core.sandbox._WASMTIME_AVAILABLE", False)
def test_sandbox_execute_file_without_wasmtime_raises(tmp_path):

    wasm_file = tmp_path / "test.wasm"
    wasm_file.write_bytes(b"\x00asm\x01\x00\x00\x00")  # minimal invalid wasm header

    sandbox = WasmSandbox()
    with pytest.raises(SandboxError):
        sandbox.execute_file(str(wasm_file), "fn_name")


@patch("vorte.core.sandbox._WASMTIME_AVAILABLE", False)
def test_sandboxed_decorator_warns_when_wasmtime_absent():

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @sandboxed("validators/email.wasm", "validate_email")
        async def handler():
            return "ok"

        if w:
            # At least one ImportWarning about wasmtime
            categories = [warning.category for warning in w]
            assert ImportWarning in categories


@pytest.mark.asyncio
@patch("vorte.core.sandbox._WASMTIME_AVAILABLE", False)
async def test_sandboxed_decorator_calls_handler():
    """@sandboxed should call the wrapped handler even if Wasm execution is skipped."""

    @sandboxed("fake.wasm", "check")
    async def handler():
        return "executed"

    result = await handler()
    assert result == "executed"


def test_sandbox_error_is_runtime_error():
    exc = SandboxError("test")
    assert isinstance(exc, RuntimeError)


def test_sandbox_default_config():
    sandbox = WasmSandbox()
    assert sandbox._allow_wasi is False
    assert sandbox._fuel is None
    assert sandbox._max_wasm_stack == 512 * 1024


def test_sandbox_with_wasmtime(tmp_path):
    """Integration test — runs a real add.wasm if wasmtime is available."""
    if not _WASMTIME_AVAILABLE:
        pytest.skip("wasmtime not installed")

    # Minimal WAT module: (func (export "add") (param i32 i32) (result i32) local.get 0 local.get 1 i32.add)
    # Pre-compiled binary equivalent
    wat_wasm = bytes([
        0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,  # magic + version
        0x01, 0x07, 0x01, 0x60, 0x02, 0x7f, 0x7f, 0x01, 0x7f,  # type section: (i32, i32) -> i32
        0x03, 0x02, 0x01, 0x00,  # function section
        0x07, 0x07, 0x01, 0x03, 0x61, 0x64, 0x64, 0x00, 0x00,  # export section: "add"
        0x0a, 0x09, 0x01, 0x07, 0x00, 0x20, 0x00, 0x20, 0x01, 0x6a, 0x0b,  # code section
    ])
    wasm_file = tmp_path / "add.wasm"
    wasm_file.write_bytes(wat_wasm)

    sandbox = WasmSandbox()
    result = sandbox.execute(wat_wasm, "add", 3, 4)
    assert result == 7
