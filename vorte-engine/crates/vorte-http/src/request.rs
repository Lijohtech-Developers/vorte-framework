use bytes::Bytes;

use crate::headers::HeaderMap;
use crate::method::Method;
use crate::raw::{RawRequest, Scheme, MAX_HEADERS, RawHeader};
use crate::parse::ParsedUri;

pub struct HttpRequest {
    buffer: Bytes,
    raw: RawRequest,
    peer_addr: Option<std::net::SocketAddr>,
    server_addr: Option<std::net::SocketAddr>,
}

impl HttpRequest {
    pub fn new(buffer: Bytes, raw: RawRequest) -> Self {
        Self {
            buffer,
            raw,
            peer_addr: None,
            server_addr: None,
        }
    }

    pub fn from_hyper(req: hyper::Request<impl hyper::body::Body>) -> Self {
        let (parts, _body) = req.into_parts();

        let method = Method::from_standard(parts.method);
        let uri = parts.uri;
        let parsed = ParsedUri::from_uri(&uri);

        let path_bytes = parsed.path.as_bytes();
        let query_bytes = parsed.query.as_bytes();

        let mut buffer = Vec::new();
        let path_offset = buffer.len();
        buffer.extend_from_slice(path_bytes);
        let path_len = buffer.len() - path_offset;

        let query_offset = buffer.len();
        buffer.extend_from_slice(query_bytes);
        let query_len = buffer.len() - query_offset;

        let mut raw_headers = [RawHeader {
            name_offset: 0,
            name_len: 0,
            value_offset: 0,
            value_len: 0,
        }; MAX_HEADERS];
        let mut header_count = 0u32;

        for (name, value) in parts.headers.iter() {
            if header_count as usize >= MAX_HEADERS {
                break;
            }
            let name_bytes = name.as_str().as_bytes();
            let name_offset = buffer.len() as u32;
            buffer.extend_from_slice(name_bytes);
            let name_len = (buffer.len() as u32 - name_offset) as u16;

            let value_bytes = value.as_bytes();
            let value_offset = buffer.len() as u32;
            buffer.extend_from_slice(value_bytes);
            let value_len = (buffer.len() as u32 - value_offset) as u16;

            raw_headers[header_count as usize] = RawHeader {
                name_offset,
                name_len,
                value_offset,
                value_len,
            };
            header_count += 1;
        }

        let buffer = Bytes::from(buffer);

        let raw = RawRequest {
            method,
            path_offset: path_offset as u32,
            path_len: path_len as u32,
            query_offset: query_offset as u32,
            query_len: query_len as u32,
            fragment_offset: 0,
            fragment_len: 0,
            version_major: 1,
            version_minor: if parts.version == http::Version::HTTP_11 { 1 } else { 0 },
            scheme: if parsed.scheme == "https" { Scheme::Https } else { Scheme::Http },
            header_count,
            body_offset: 0,
            body_len: 0,
            headers: raw_headers,
        };

        Self {
            buffer,
            raw,
            peer_addr: None,
            server_addr: None,
        }
    }

    #[inline]
    pub fn method(&self) -> Method {
        self.raw.method
    }

    #[inline]
    pub fn path(&self) -> &str {
        self.raw.path(&self.buffer)
    }

    #[inline]
    pub fn query_string(&self) -> &[u8] {
        self.raw.query(&self.buffer)
    }

    #[inline]
    pub fn scheme(&self) -> Scheme {
        self.raw.scheme
    }

    #[inline]
    pub fn http_version(&self) -> (u8, u8) {
        self.raw.http_version()
    }

    pub fn header_map(&self) -> HeaderMap {
        let mut map = HeaderMap::new();
        for i in 0..self.raw.header_count as usize {
            let rh = &self.raw.headers[i];
            let name = rh.name(&self.buffer);
            let value = rh.value(&self.buffer);
            map.append_raw(name, value);
        }
        map
    }

    pub fn header(&self, name: &[u8]) -> Option<&[u8]> {
        for i in 0..self.raw.header_count as usize {
            let rh = &self.raw.headers[i];
            let hname = rh.name(&self.buffer);
            if hname.eq_ignore_ascii_case(name) {
                return Some(rh.value(&self.buffer));
            }
        }
        None
    }

    pub fn content_type(&self) -> Option<&[u8]> {
        self.header(b"content-type")
    }

    pub fn content_length(&self) -> Option<u64> {
        self.header(b"content-length")
            .and_then(|v| std::str::from_utf8(v).ok())
            .and_then(|v| v.parse().ok())
    }

    pub fn with_peer_addr(mut self, addr: std::net::SocketAddr) -> Self {
        self.peer_addr = Some(addr);
        self
    }

    pub fn with_server_addr(mut self, addr: std::net::SocketAddr) -> Self {
        self.server_addr = Some(addr);
        self
    }

    pub fn peer_addr(&self) -> Option<&std::net::SocketAddr> {
        self.peer_addr.as_ref()
    }

    pub fn server_addr(&self) -> Option<&std::net::SocketAddr> {
        self.server_addr.as_ref()
    }

    pub fn buffer(&self) -> &Bytes {
        &self.buffer
    }

    pub fn raw(&self) -> &RawRequest {
        &self.raw
    }
}
