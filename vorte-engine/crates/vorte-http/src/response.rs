use bytes::Bytes;
use http_body_util::Full;

#[derive(Debug)]
pub struct HttpResponse {
    status: u16,
    headers: Vec<(String, Vec<u8>)>,
    body: Bytes,
}

impl HttpResponse {
    pub fn new(status: u16) -> Self {
        Self {
            status,
            headers: Vec::new(),
            body: Bytes::new(),
        }
    }

    pub fn ok(body: impl Into<Bytes>) -> Self {
        Self {
            status: 200,
            headers: Vec::new(),
            body: body.into(),
        }
    }

    pub fn status(mut self, status: u16) -> Self {
        self.status = status;
        self
    }

    pub fn header(mut self, name: impl Into<String>, value: impl Into<Vec<u8>>) -> Self {
        self.headers.push((name.into(), value.into()));
        self
    }

    pub fn body(mut self, body: impl Into<Bytes>) -> Self {
        self.body = body.into();
        self
    }

    pub fn json(self, data: &[u8]) -> Self {
        self.header("content-type", b"application/json".to_vec())
            .body(data.to_vec())
    }

    pub fn text(self, data: &[u8]) -> Self {
        self.header("content-type", b"text/plain; charset=utf-8".to_vec())
            .body(data.to_vec())
    }

    pub fn html(self, data: &[u8]) -> Self {
        self.header("content-type", b"text/html; charset=utf-8".to_vec())
            .body(data.to_vec())
    }

    pub fn status_code(&self) -> u16 {
        self.status
    }

    pub fn headers(&self) -> &[(String, Vec<u8>)] {
        &self.headers
    }

    pub fn body_bytes(&self) -> &Bytes {
        &self.body
    }

    pub fn into_hyper(self) -> hyper::Response<Full<Bytes>> {
        let mut builder = http::Response::builder()
            .status(self.status);

        for (name, value) in self.headers {
            builder = builder.header(&name, value.as_slice());
        }

        builder
            .body(Full::new(self.body))
            .unwrap_or_else(|_| {
                http::Response::builder()
                    .status(500)
                    .body(Full::new(Bytes::from("Internal Server Error")))
                    .unwrap()
            })
    }

    pub fn not_found() -> Self {
        Self {
            status: 404,
            headers: vec![("content-type".into(), b"application/json".to_vec())],
            body: Bytes::from(r#"{"detail":"Not Found"}"#),
        }
    }

    pub fn internal_error() -> Self {
        Self {
            status: 500,
            headers: vec![("content-type".into(), b"application/json".to_vec())],
            body: Bytes::from(r#"{"detail":"Internal Server Error"}"#),
        }
    }

    pub fn method_not_allowed() -> Self {
        Self {
            status: 405,
            headers: vec![("content-type".into(), b"application/json".to_vec())],
            body: Bytes::from(r#"{"detail":"Method Not Allowed"}"#),
        }
    }
}

pub struct ResponseBuilder {
    status: u16,
    headers: Vec<(String, Vec<u8>)>,
    body: Vec<u8>,
    started: bool,
    complete: bool,
}

impl ResponseBuilder {
    pub fn new() -> Self {
        Self {
            status: 200,
            headers: Vec::new(),
            body: Vec::new(),
            started: false,
            complete: false,
        }
    }

    pub fn apply_response_start(&mut self, status: u16, headers: Vec<(String, Vec<u8>)>) {
        if !self.started {
            self.status = status;
            self.headers = headers;
            self.started = true;
        }
    }

    pub fn append_body(&mut self, data: &[u8]) {
        self.body.extend_from_slice(data);
    }

    pub fn mark_complete(&mut self) {
        self.complete = true;
    }

    pub fn is_complete(&self) -> bool {
        self.complete
    }

    pub fn build(self) -> HttpResponse {
        HttpResponse {
            status: self.status,
            headers: self.headers,
            body: Bytes::from(self.body),
        }
    }
}
