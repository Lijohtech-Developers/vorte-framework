use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Instant;

use bytes::Bytes;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
use pyo3::prelude::*;
use tracing::{debug, error};

use vorte_core::pipeline::HandlerFn;
use vorte_http::{HttpResponse, Method};
use vorte_router::MatchResult;

use crate::bridge::{build_asgi_scope, create_asgi_callables, run_asgi_call};
use crate::metrics::{MetricsBuffer, Span};

pub fn create_python_handler(app: Py<PyAny>, metrics: MetricsBuffer) -> HandlerFn {
    let app_arc = Arc::new(app);
    Arc::new(move |req: hyper::Request<Incoming>,
                   method: Method,
                   path: &str,
                   match_result: &MatchResult,
                   peer_addr: SocketAddr,
                   server_addr: Option<SocketAddr>| {
        let app = app_arc.clone();
        let path_owned = path.to_owned();
        let params = match_result.params.clone();
        let metrics = metrics.clone();

        Box::pin(async move {
            let (parts, body) = req.into_parts();

            let query = parts.uri.query().unwrap_or("").to_owned();

            let http_version = if parts.version == http::Version::HTTP_11 {
                (1, 1)
            } else if parts.version == http::Version::HTTP_2 {
                (2, 0)
            } else if parts.version == http::Version::HTTP_10 {
                (1, 0)
            } else {
                (1, 1)
            };

            let headers: Vec<(String, Vec<u8>)> = parts
                .headers
                .iter()
                .map(|(name, value)| (name.as_str().to_owned(), value.as_bytes().to_vec()))
                .collect();

            let body_bytes = match body.collect().await {
                Ok(collected) => collected.to_bytes().to_vec(),
                Err(e) => {
                    error!("Failed to read request body: {}", e);
                    return HttpResponse::internal_error().into_hyper();
                }
            };

            let result = tokio::task::spawn_blocking(move || {
                Python::with_gil(|py| {
                    let t0 = Instant::now();
                    let response = match handle_request_python(
                        py,
                        &*app,
                        method,
                        &path_owned,
                        &query,
                        &headers,
                        &body_bytes,
                        peer_addr,
                        server_addr,
                        http_version,
                        &params,
                    ) {
                        Ok(r) => r,
                        Err(e) => {
                            error!("Python handler error: {}", e);
                            HttpResponse::internal_error().into_hyper()
                        }
                    };
                    let latency_ns = t0.elapsed().as_nanos() as u64;
                    let status = response.status().as_u16();
                    metrics.push(Span {
                        method: method.as_str().to_owned(),
                        path: path_owned.clone(),
                        status,
                        latency_ns,
                    });
                    response
                })
            })
            .await;

            match result {
                Ok(response) => response,
                Err(e) => {
                    error!("Blocking task error: {}", e);
                    HttpResponse::internal_error().into_hyper()
                }
            }
        })
    })
}

fn handle_request_python(
    py: Python,
    app: &Py<PyAny>,
    method: Method,
    path: &str,
    query: &str,
    headers: &[(String, Vec<u8>)],
    body: &[u8],
    peer_addr: SocketAddr,
    server_addr: Option<SocketAddr>,
    http_version: (u8, u8),
    params: &vorte_router::Params,
) -> PyResult<hyper::Response<Full<Bytes>>> {
    let scope = build_asgi_scope(
        py,
        method,
        path,
        query,
        headers,
        Some(peer_addr),
        server_addr,
        http_version,
        params,
    )?;

    let (receive, send, response_state) = create_asgi_callables(py, body)?;

    match run_asgi_call(py, app, scope, receive, send) {
        Ok(()) => {}
        Err(e) => {
            debug!("ASGI handler returned error: {}", e);
        }
    }

    let state = response_state
        .lock()
        .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("Response state poisoned"))?;

    let status = state.status;
    let resp_headers = state.headers.clone();
    let resp_body = state.body.clone();

    let mut builder = http::Response::builder().status(status);
    for (name, value) in resp_headers {
        builder = builder.header(&name, value.as_slice());
    }

    Ok(builder
        .body(Full::new(Bytes::from(resp_body)))
        .unwrap_or_else(|_| {
            http::Response::builder()
                .status(500)
                .body(Full::new(Bytes::from("Internal Server Error")))
                .unwrap()
        }))
}
