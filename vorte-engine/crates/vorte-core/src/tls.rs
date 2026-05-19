use std::sync::Arc;

use tokio::net::TcpStream;
use tracing::{debug, info, warn};

pub struct TlsConfig {
    cert_path: String,
    key_path: String,
}

impl TlsConfig {
    pub fn from_paths(cert: impl Into<String>, key: impl Into<String>) -> Self {
        Self {
            cert_path: cert.into(),
            key_path: key.into(),
        }
    }

    pub async fn build_acceptor(
        &self,
    ) -> Result<tokio_rustls::TlsAcceptor, Box<dyn std::error::Error + Send + Sync>> {
        let cert_file = std::fs::File::open(&self.cert_path)?;
        let mut cert_reader = std::io::BufReader::new(cert_file);
        let certs: Vec<rustls::pki_types::CertificateDer<'_>> =
            rustls_pemfile::certs(&mut cert_reader)
                .collect::<Result<Vec<_>, _>>()?;

        let key_file = std::fs::File::open(&self.key_path)?;
        let mut key_reader = std::io::BufReader::new(key_file);
        let key = rustls_pemfile::private_key(&mut key_reader)?
            .ok_or("No private key found")?;

        let mut config = rustls::ServerConfig::builder()
            .with_no_client_auth()
            .with_single_cert(certs, key)?;

        config.alpn_protocols = vec![b"h2".to_vec(), b"http/1.1".to_vec()];

        let config = Arc::new(config);
        Ok(tokio_rustls::TlsAcceptor::from(config))
    }
}

pub async fn wrap_stream(
    acceptor: &tokio_rustls::TlsAcceptor,
    stream: TcpStream,
) -> Result<tokio_rustls::server::TlsStream<TcpStream>, Box<dyn std::error::Error + Send + Sync>> {
    let tls_stream = acceptor.accept(stream).await?;
    Ok(tls_stream)
}
