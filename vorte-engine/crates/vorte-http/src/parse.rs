use std::str;

use smallvec::SmallVec;

pub struct ParsedUri {
    pub scheme: &'static str,
    pub path: String,
    pub query: String,
    pub fragment: String,
}

impl ParsedUri {
    pub fn from_uri(uri: &http::Uri) -> Self {
        let path = uri.path().to_owned();
        let query = uri.query().unwrap_or("").to_owned();
        let scheme = match uri.scheme_str() {
            Some("https") => "https",
            _ => "http",
        };

        Self {
            scheme,
            path,
            query,
            fragment: String::new(),
        }
    }

    pub fn from_bytes(raw: &[u8]) -> Self {
        let s = str::from_utf8(raw).unwrap_or("/");
        Self::from_str(s)
    }

    pub fn from_str(raw: &str) -> Self {
        let (path_and_query, fragment) = match raw.find('#') {
            Some(pos) => (&raw[..pos], raw[pos + 1..].to_owned()),
            None => (raw, String::new()),
        };

        let (path, query) = match path_and_query.find('?') {
            Some(pos) => (path_and_query[..pos].to_owned(), path_and_query[pos + 1..].to_owned()),
            None => (path_and_query.to_owned(), String::new()),
        };

        Self {
            scheme: "http",
            path,
            query,
            fragment,
        }
    }
}

pub struct QueryParam {
    pub key: (usize, usize),
    pub value: (usize, usize),
}

pub fn parse_query_string(query: &[u8]) -> SmallVec<[QueryParam; 16]> {
    let mut params: SmallVec<[QueryParam; 16]> = SmallVec::new();
    if query.is_empty() {
        return params;
    }

    let mut start = 0;
    while start < query.len() {
        let eq_pos = query[start..]
            .iter()
            .position(|&b| b == b'=')
            .map(|p| start + p);

        let amp_pos = query[start..]
            .iter()
            .position(|&b| b == b'&')
            .map(|p| start + p);

        let end = amp_pos.unwrap_or(query.len());

        if let Some(eq) = eq_pos {
            if eq < end {
                params.push(QueryParam {
                    key: (start, eq - start),
                    value: (eq + 1, end - eq - 1),
                });
            }
        }

        start = match amp_pos {
            Some(p) => p + 1,
            None => break,
        };
    }

    params
}

pub fn decode_percent(src: &[u8]) -> Vec<u8> {
    let mut dst = Vec::with_capacity(src.len());
    let mut i = 0;
    while i < src.len() {
        if src[i] == b'%' && i + 2 < src.len() {
            if let (Some(hi), Some(lo)) = (hex_digit(src[i + 1]), hex_digit(src[i + 2])) {
                dst.push(hi << 4 | lo);
                i += 3;
                continue;
            }
        } else if src[i] == b'+' {
            dst.push(b' ');
            i += 1;
            continue;
        }
        dst.push(src[i]);
        i += 1;
    }
    dst
}

#[inline]
fn hex_digit(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_uri() {
        let parsed = ParsedUri::from_str("/users/123?page=1#top");
        assert_eq!(parsed.path, "/users/123");
        assert_eq!(parsed.query, "page=1");
        assert_eq!(parsed.fragment, "top");
    }

    #[test]
    fn test_parse_query() {
        let params = parse_query_string(b"name=alice&age=30");
        assert_eq!(params.len(), 2);
    }

    #[test]
    fn test_percent_decode() {
        assert_eq!(decode_percent(b"hello%20world"), b"hello world");
        assert_eq!(decode_percent(b"a%2Bb"), b"a+b");
    }
}
