use std::fmt;


#[repr(C)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Method {
    Get = 0,
    Post = 1,
    Put = 2,
    Delete = 3,
    Patch = 4,
    Head = 5,
    Options = 6,
    Trace = 7,
    Connect = 8,
}

impl Method {
    #[inline]
    pub fn from_bytes(bytes: &[u8]) -> Option<Self> {
        match bytes {
            b"GET" => Some(Method::Get),
            b"POST" => Some(Method::Post),
            b"PUT" => Some(Method::Put),
            b"DELETE" => Some(Method::Delete),
            b"PATCH" => Some(Method::Patch),
            b"HEAD" => Some(Method::Head),
            b"OPTIONS" => Some(Method::Options),
            b"TRACE" => Some(Method::Trace),
            b"CONNECT" => Some(Method::Connect),
            _ => None,
        }
    }

    #[inline]
    pub fn from_standard(code: http::Method) -> Self {
        if code == http::Method::GET {
            Method::Get
        } else if code == http::Method::POST {
            Method::Post
        } else if code == http::Method::PUT {
            Method::Put
        } else if code == http::Method::DELETE {
            Method::Delete
        } else if code == http::Method::PATCH {
            Method::Patch
        } else if code == http::Method::HEAD {
            Method::Head
        } else if code == http::Method::OPTIONS {
            Method::Options
        } else if code == http::Method::TRACE {
            Method::Trace
        } else if code == http::Method::CONNECT {
            Method::Connect
        } else {
            Method::Get
        }
    }

    #[inline]
    pub fn as_str(&self) -> &'static str {
        match self {
            Method::Get => "GET",
            Method::Post => "POST",
            Method::Put => "PUT",
            Method::Delete => "DELETE",
            Method::Patch => "PATCH",
            Method::Head => "HEAD",
            Method::Options => "OPTIONS",
            Method::Trace => "TRACE",
            Method::Connect => "CONNECT",
        }
    }

    #[inline]
    pub fn to_http_method(&self) -> http::Method {
        match self {
            Method::Get => http::Method::GET,
            Method::Post => http::Method::POST,
            Method::Put => http::Method::PUT,
            Method::Delete => http::Method::DELETE,
            Method::Patch => http::Method::PATCH,
            Method::Head => http::Method::HEAD,
            Method::Options => http::Method::OPTIONS,
            Method::Trace => http::Method::TRACE,
            Method::Connect => http::Method::CONNECT,
        }
    }

    pub const fn count() -> usize {
        9
    }

    pub fn from_index(index: usize) -> Option<Self> {
        match index {
            0 => Some(Method::Get),
            1 => Some(Method::Post),
            2 => Some(Method::Put),
            3 => Some(Method::Delete),
            4 => Some(Method::Patch),
            5 => Some(Method::Head),
            6 => Some(Method::Options),
            7 => Some(Method::Trace),
            8 => Some(Method::Connect),
            _ => None,
        }
    }
}

impl fmt::Display for Method {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}
