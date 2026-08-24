//! Mobiscout Core - High-Performance Rust Engine
//!
//! CPU-hot operations for the Mobiscout framework, exposed to Python over PyO3.
//!
//! # Modules
//!
//! - `ast_analyzer`: tree-sitter AST parsing and complexity analysis (`RustAstAnalyzer`)
//! - `sast_scan`: multi-pattern line scanner for SAST (`scan_lines`, RegexSet + rayon)

use pyo3::prelude::*;

// Module declarations
pub mod ast_analyzer;
pub mod sast_scan;
pub mod utils;

// Re-exports
pub use ast_analyzer::{ComplexityMetrics, RustAstAnalyzer};

/// Python module definition
#[pymodule]
fn mobiscout_core(_py: Python, m: &PyModule) -> PyResult<()> {
    // Initialize logging
    env_logger::init();

    // Register classes
    m.add_class::<RustAstAnalyzer>()?;
    m.add_class::<ComplexityMetrics>()?;

    // Register the SAST multi-pattern line scanner (RegexSet, parallel over files)
    m.add_function(wrap_pyfunction!(sast_scan::scan_lines, m)?)?;

    // Module metadata
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__author__", "Vadim Toptunov")?;

    Ok(())
}

// No Rust `#[cfg(test)]` here: the crate is a PyO3 `extension-module`, so a standalone
// `cargo test` binary can't resolve the interpreter symbols (it aborts on `_PyExc_*`). The
// old `test_module_loads` (`assert!(true)`) never actually ran and proved nothing. The core
// is exercised for real from Python — `tests/test_native_scan.py` (scan_lines parity) and
// `tests/test_native_analyzer.py` (the analyzer seam) — plus the build-engine smoke test
// that imports the built wheel and asserts the backend reports "rust".
