try:
    try:
        from vorte._vorte_engine import VorteEngine as _NativeVorteEngine
    except ImportError:
        from _vorte_engine import VorteEngine as _NativeVorteEngine
    _NATIVE_AVAILABLE = True
except ImportError:
    _NATIVE_AVAILABLE = False


class VorteEngine:
    def __init__(self, app=None, *, host="0.0.0.0", port=8000, workers=1):
        self._app = app
        self._host = host
        self._port = port
        self._workers = workers

        if _NATIVE_AVAILABLE and app is not None:
            self._engine = _NativeVorteEngine()
            self._register_routes(app)
        else:
            self._engine = None

    def _register_routes(self, app):
        actual_app = app
        if hasattr(app, 'fastapi'):
            actual_app = app.fastapi

        if hasattr(actual_app, 'routes'):
            from fastapi.routing import APIRoute
            for route in actual_app.routes:
                if isinstance(route, APIRoute):
                    for method in (route.methods or set()):
                        self._engine.add_route(method, route.path)

        if hasattr(app, 'include_router'):
            pass

    def add_route(self, method: str, path: str):
        if self._engine is not None:
            self._engine.add_route(method, path)
        return self

    def run(self, app=None, *, host=None, port=None, workers=None):
        target_app = app or self._app
        if target_app is None:
            raise ValueError("No application provided. Pass app to VorteEngine() or run().")

        run_host = host or self._host
        run_port = port or self._port
        run_workers = workers or self._workers

        if self._engine is not None:
            actual_app = target_app
            if hasattr(target_app, 'fastapi'):
                pass
            self._engine.run(actual_app, run_host, run_port, run_workers)
        else:
            import uvicorn
            uvicorn.run(target_app, host=run_host, port=run_port, workers=run_workers)

    @property
    def is_native(self) -> bool:
        return self._engine is not None

    @property
    def route_count(self) -> int:
        if self._engine is not None:
            return self._engine.route_count
        return 0
