use std::sync::{Arc, Mutex};

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple};

use vorte_http::Method;
use vorte_router::Params;

pub struct ResponseState {
    pub status: u16,
    pub headers: Vec<(String, Vec<u8>)>,
    pub body: Vec<u8>,
    pub started: bool,
    pub _complete: bool,
}

impl ResponseState {
    pub fn new() -> Self {
        Self {
            status: 200,
            headers: Vec::new(),
            body: Vec::new(),
            started: false,
            _complete: false,
        }
    }
}

#[pyclass]
pub struct AsgiReceive {
    body: Vec<u8>,
    consumed: std::sync::atomic::AtomicBool,
}

#[pymethods]
impl AsgiReceive {
    #[pyo3(signature = ())]
    fn __call__(&self, py: Python) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new_bound(py);

        if !self
            .consumed
            .swap(true, std::sync::atomic::Ordering::SeqCst)
        {
            dict.set_item("type", "http.request")?;
            dict.set_item("body", PyBytes::new_bound(py, &self.body))?;
            dict.set_item("more_body", false)?;
        } else {
            dict.set_item("type", "http.disconnect")?;
        }

        Ok(dict.into_any().unbind())
    }
}

#[pyclass]
pub struct AsgiSend {
    state: Arc<Mutex<ResponseState>>,
}

#[pymethods]
impl AsgiSend {
    fn __call__(&self, _py: Python, message: &Bound<'_, PyDict>) -> PyResult<()> {
        let msg_type: String = message
            .get_item("type")?
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Missing 'type' in ASGI message"))?
            .extract()?;

        let mut state = self.state.lock().map_err(|_| {
            pyo3::exceptions::PyRuntimeError::new_err("Response state lock poisoned")
        })?;

        match msg_type.as_str() {
            "http.response.start" => {
                let status: u16 = message
                    .get_item("status")?
                    .ok_or_else(|| {
                        pyo3::exceptions::PyValueError::new_err("Missing 'status' in response.start")
                    })?
                    .extract()?;

                let mut headers = Vec::new();
                if let Some(raw_headers) = message.get_item("headers")? {
                    let header_list = raw_headers.downcast::<PyList>()?;
                    for item in header_list.iter() {
                        let tuple = item.downcast::<PyTuple>()?;
                        let name_bound = tuple.get_item(0)?;
                        let name: &[u8] = name_bound.extract()?;
                        let value_bound = tuple.get_item(1)?;
                        let value: &[u8] = value_bound.extract()?;
                        headers.push((
                            std::str::from_utf8(name)
                                .unwrap_or("unknown")
                                .to_owned(),
                            value.to_vec(),
                        ));
                    }
                }

                state.status = status;
                state.headers = headers;
                state.started = true;
            }
            "http.response.body" => {
                if let Some(body_data) = message.get_item("body")? {
                    let data: &[u8] = body_data.extract()?;
                    state.body.extend_from_slice(data);
                }
            }
            _ => {}
        }

        Ok(())
    }
}

pub fn create_asgi_callables(
    py: Python,
    body: &[u8],
) -> PyResult<(Py<AsgiReceive>, Py<AsgiSend>, Arc<Mutex<ResponseState>>)> {
    let response_state = Arc::new(Mutex::new(ResponseState::new()));

    let receive = Py::new(
        py,
        AsgiReceive {
            body: body.to_vec(),
            consumed: std::sync::atomic::AtomicBool::new(false),
        },
    )?;

    let send = Py::new(
        py,
        AsgiSend {
            state: response_state.clone(),
        },
    )?;

    Ok((receive, send, response_state))
}

pub fn build_asgi_scope(
    py: Python,
    method: Method,
    path: &str,
    query: &str,
    headers: &[(String, Vec<u8>)],
    peer_addr: Option<std::net::SocketAddr>,
    server_addr: Option<std::net::SocketAddr>,
    http_version: (u8, u8),
    params: &Params,
) -> PyResult<Py<PyDict>> {
    let scope = PyDict::new_bound(py);

    scope.set_item("type", "http")?;

    let asgi = PyDict::new_bound(py);
    asgi.set_item("version", "3.0")?;
    asgi.set_item("spec_version", "2.3")?;
    scope.set_item("asgi", asgi)?;

    scope.set_item(
        "http_version",
        format!("{}.{}", http_version.0, http_version.1),
    )?;
    scope.set_item("method", method.as_str())?;
    scope.set_item("scheme", "http")?;
    scope.set_item("path", path)?;
    scope.set_item("query_string", PyBytes::new_bound(py, query.as_bytes()))?;
    scope.set_item("root_path", "")?;

    let header_list = PyList::empty_bound(py);
    for (name, value) in headers {
        let mut name_lower = name.as_bytes().to_vec();
        name_lower.make_ascii_lowercase();
        header_list.append((
            PyBytes::new_bound(py, &name_lower),
            PyBytes::new_bound(py, value),
        ))?;
    }
    scope.set_item("headers", header_list)?;

    if let Some(addr) = server_addr {
        scope.set_item("server", (addr.ip().to_string(), addr.port()))?;
    }

    if let Some(addr) = peer_addr {
        scope.set_item("client", (addr.ip().to_string(), addr.port()))?;
    }

    let path_params = PyDict::new_bound(py);
    let normalized = if path.starts_with('/') { &path[1..] } else { path };
    let trimmed = if normalized.ends_with('/') && normalized.len() > 1 {
        &normalized[..normalized.len() - 1]
    } else {
        normalized
    };
    for param in params.iter() {
        let value = param.value(trimmed);
        path_params.set_item(&param.key, value)?;
    }
    scope.set_item("path_params", path_params)?;

    Ok(scope.unbind())
}

pub fn run_asgi_call(
    py: Python,
    app: &Py<PyAny>,
    scope: Py<PyDict>,
    receive: Py<AsgiReceive>,
    send: Py<AsgiSend>,
) -> PyResult<()> {
    let asyncio = py.import_bound("asyncio")?;

    let loop_ = asyncio.call_method0("new_event_loop")?;
    asyncio.call_method1("set_event_loop", (&loop_,))?;

    let scope_ref = scope.bind(py);
    let receive_ref = receive.bind(py);
    let send_ref = send.bind(py);

    let coro = app
        .bind(py)
        .call1((scope_ref, receive_ref, send_ref))?;

    loop_.call_method1("run_until_complete", (coro,))?;

    Ok(())
}
