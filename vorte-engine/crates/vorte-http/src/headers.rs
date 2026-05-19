use std::fmt;

pub struct HeaderMap {
    entries: Vec<HeaderEntry>,
}

struct HeaderEntry {
    name: Box<[u8]>,
    value: Box<[u8]>,
    hash: u64,
}

impl HeaderMap {
    pub fn new() -> Self {
        Self {
            entries: Vec::with_capacity(32),
        }
    }

    pub fn with_capacity(cap: usize) -> Self {
        Self {
            entries: Vec::with_capacity(cap),
        }
    }

    pub fn append(&mut self, name: impl AsRef<[u8]>, value: impl AsRef<[u8]>) {
        let name = name.as_ref();
        let value = value.as_ref();
        self.entries.push(HeaderEntry {
            hash: hash_ignore_case(name),
            name: name.into(),
            value: value.into(),
        });
    }

    pub fn append_raw(&mut self, name: &[u8], value: &[u8]) {
        self.entries.push(HeaderEntry {
            hash: hash_ignore_case(name),
            name: name.into(),
            value: value.into(),
        });
    }

    pub fn get(&self, name: &[u8]) -> Option<&[u8]> {
        let target_hash = hash_ignore_case(name);
        for entry in &self.entries {
            if entry.hash == target_hash && entry.name.eq_ignore_ascii_case(name) {
                return Some(&entry.value);
            }
        }
        None
    }

    pub fn get_str(&self, name: &str) -> Option<&str> {
        self.get(name.as_bytes())
            .and_then(|v| std::str::from_utf8(v).ok())
    }

    pub fn get_all(&self, name: &[u8]) -> Vec<&[u8]> {
        let target_hash = hash_ignore_case(name);
        self.entries
            .iter()
            .filter(|e| e.hash == target_hash && e.name.eq_ignore_ascii_case(name))
            .map(|e| e.value.as_ref())
            .collect()
    }

    pub fn contains(&self, name: &[u8]) -> bool {
        let target_hash = hash_ignore_case(name);
        self.entries
            .iter()
            .any(|e| e.hash == target_hash && e.name.eq_ignore_ascii_case(name))
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn iter(&self) -> HeaderIter<'_> {
        HeaderIter {
            inner: self.entries.iter(),
        }
    }

    pub fn into_asgi_headers(&self) -> Vec<(Vec<u8>, Vec<u8>)> {
        self.entries
            .iter()
            .map(|e| {
                let mut name = e.name.to_vec();
                name.make_ascii_lowercase();
                (name, e.value.to_vec())
            })
            .collect()
    }
}

pub struct HeaderIter<'a> {
    inner: std::slice::Iter<'a, HeaderEntry>,
}

impl<'a> Iterator for HeaderIter<'a> {
    type Item = (&'a [u8], &'a [u8]);

    fn next(&mut self) -> Option<Self::Item> {
        self.inner.next().map(|e| (e.name.as_ref(), e.value.as_ref()))
    }
}

impl fmt::Debug for HeaderMap {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("HeaderMap")
            .field("count", &self.entries.len())
            .finish()
    }
}

#[inline]
fn hash_ignore_case(data: &[u8]) -> u64 {
    let mut hash: u64 = 5381;
    for &byte in data {
        hash = hash.wrapping_mul(33).wrapping_add((byte | 0x20) as u64);
    }
    hash
}

impl Default for HeaderMap {
    fn default() -> Self {
        Self::new()
    }
}
