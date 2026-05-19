use crate::Method;

#[repr(C)]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Scheme {
    Http = 0,
    Https = 1,
   Ws = 2,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct RawHeader {
    pub name_offset: u32,
    pub name_len: u16,
    pub value_offset: u32,
    pub value_len: u16,
}

impl RawHeader {
    pub fn name<'a>(&self, buffer: &'a [u8]) -> &'a [u8] {
        let start = self.name_offset as usize;
        let end = start + self.name_len as usize;
        &buffer[start..end]
    }

    pub fn value<'a>(&self, buffer: &'a [u8]) -> &'a [u8] {
        let start = self.value_offset as usize;
        let end = start + self.value_len as usize;
        &buffer[start..end]
    }
}

pub const MAX_HEADERS: usize = 96;

#[repr(C)]
pub struct RawRequest {
    pub method: Method,
    pub path_offset: u32,
    pub path_len: u32,
    pub query_offset: u32,
    pub query_len: u32,
    pub fragment_offset: u32,
    pub fragment_len: u32,
    pub version_major: u8,
    pub version_minor: u8,
    pub scheme: Scheme,
    pub header_count: u32,
    pub body_offset: u32,
    pub body_len: u32,
    pub headers: [RawHeader; MAX_HEADERS],
}

impl RawRequest {
    pub fn path<'a>(&self, buffer: &'a [u8]) -> &'a str {
        let start = self.path_offset as usize;
        let end = start + self.path_len as usize;
        unsafe { std::str::from_utf8_unchecked(&buffer[start..end]) }
    }

    pub fn query<'a>(&self, buffer: &'a [u8]) -> &'a [u8] {
        let start = self.query_offset as usize;
        let end = start + self.query_len as usize;
        &buffer[start..end]
    }

    pub fn body<'a>(&self, buffer: &'a [u8]) -> &'a [u8] {
        let start = self.body_offset as usize;
        let end = start + self.body_len as usize;
        &buffer[start..end]
    }

    pub fn http_version(&self) -> (u8, u8) {
        (self.version_major, self.version_minor)
    }
}

unsafe impl Send for RawRequest {}
unsafe impl Sync for RawRequest {}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct RawResponse {
    pub status_code: u16,
    pub header_count: u32,
    pub body_offset: u32,
    pub body_len: u32,
    pub headers: [RawHeader; MAX_HEADERS],
}
