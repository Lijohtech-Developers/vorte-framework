use pyo3::prelude::*;

mod bridge;
mod engine;
mod handler;
mod metrics;

use crate::engine::VorteEngine;
use crate::metrics::MetricsCollector;

#[pymodule]
fn _vorte_engine(m: &Bound<'_, pyo3::types::PyModule>) -> PyResult<()> {
    m.add_class::<VorteEngine>()?;
    m.add_class::<MetricsCollector>()?;
    Ok(())
}
