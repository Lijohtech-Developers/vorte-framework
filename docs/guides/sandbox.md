# WASM Sandbox

Vorte includes a WebAssembly sandbox for executing untrusted code in isolation.

## Requirements

```bash
pip install vorte[sandbox]
```

This installs `wasmtime>=25.0.0`.

## WasmSandbox

```python
from vorte import WasmSandbox

sandbox = WasmSandbox(
    allow_wasi=False,        # Disable host I/O (default)
    fuel=None,               # No fuel limit
    max_wasm_stack=524288,   # 512KB stack (default)
)

print(sandbox.is_available)  # True if wasmtime is installed
```

### Executing Wasm Modules

```python
# From bytes
with open("module.wasm", "rb") as f:
    wasm_bytes = f.read()

result = sandbox.execute(wasm_bytes, "add", 3, 4)
# Returns: 7

# From file
result = sandbox.execute_file("module.wasm", "add", 3, 4)
```

Each execution:
1. Creates a fresh Wasm store
2. Instantiates the module
3. Calls the exported function
4. Discards the store (full isolation)

### Security Model

- **WASI disabled by default** -- No file system, network, or environment access
- **Fuel limits** -- Optional instruction count limit
- **Stack limits** -- Configurable maximum Wasm stack size
- **Fresh store per execution** -- No state leakage between calls

## @sandboxed Decorator

Use the `@sandboxed` decorator on routes to execute a Wasm module before the Python handler:

```python
from vorte import sandboxed

@sandboxed("validators/input.wasm", "validate")
@app.post("/api/v1/data")
async def process_data(request):
    # Wasm validator runs first
    # If validation fails, the request is rejected
    return success_response(data={...})
```

The decorator:
- Sets `_vorte_sandboxed = True` on the function
- Sets `_vorte_wasm_path` and `_vorte_wasm_fn`
- Emits `ImportWarning` if wasmtime is not installed
- Falls through to the Python handler if wasmtime is unavailable

## SandboxError

```python
from vorte.core.sandbox import SandboxError

try:
    result = sandbox.execute(wasm_bytes, "run")
except SandboxError as e:
    print(f"Sandbox error: {e}")
```

## Example: C to Wasm

```c
// add.c
int add(int a, int b) {
    return a + b;
}
```

```bash
# Compile to Wasm
clang --target=wasm32 -nostdlib -Wl,--no-entry -o add.wasm add.c
```

```python
sandbox = WasmSandbox()
result = sandbox.execute_file("add.wasm", "add", 3, 4)
assert result == 7
```
