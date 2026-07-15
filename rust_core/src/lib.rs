//! Mobiscout Core - High-Performance Rust Engine
//!
//! This library provides high-performance implementations of CPU-intensive
//! operations for the Mobile Test Recorder framework.
//!
//! # Modules
//!
//! - `ast_analyzer`: Fast AST parsing and complexity analysis
//! - `correlator`: Event correlation engine
//! - `business_logic`: Business logic pattern extraction
//! - `io`: Optimized file I/O operations

use pyo3::prelude::*;

// Module declarations
pub mod ast_analyzer;
pub mod correlator;
pub mod business_logic;
pub mod io;
pub mod utils;

// Re-exports
pub use ast_analyzer::{RustAstAnalyzer, ComplexityMetrics};
pub use correlator::{RustCorrelator, Event, Correlation};
pub use business_logic::{RustBusinessLogicAnalyzer, BusinessLogicPattern};

/// Python module definition
#[pymodule]
fn mobiscout_core(_py: Python, m: &PyModule) -> PyResult<()> {
    // Initialize logging
    env_logger::init();

    // Register classes
    m.add_class::<RustAstAnalyzer>()?;
    m.add_class::<ComplexityMetrics>()?;
    m.add_class::<RustCorrelator>()?;
    m.add_class::<Event>()?;
    m.add_class::<Correlation>()?;
    m.add_class::<RustBusinessLogicAnalyzer>()?;
    m.add_class::<BusinessLogicPattern>()?;

    // Register I/O functions
    m.add_function(wrap_pyfunction!(io::read_file_fast, m)?)?;
    m.add_function(wrap_pyfunction!(io::write_file_fast, m)?)?;
    m.add_function(wrap_pyfunction!(io::read_files_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(io::find_files, m)?)?;
    m.add_function(wrap_pyfunction!(io::get_file_size, m)?)?;
    m.add_function(wrap_pyfunction!(io::file_exists, m)?)?;
    m.add_function(wrap_pyfunction!(io::get_directory_size, m)?)?;
    m.add_function(wrap_pyfunction!(io::list_directory, m)?)?;
    m.add_function(wrap_pyfunction!(io::copy_file_fast, m)?)?;
    m.add_function(wrap_pyfunction!(io::move_file, m)?)?;
    m.add_function(wrap_pyfunction!(io::delete_file, m)?)?;
    m.add_function(wrap_pyfunction!(io::create_directory, m)?)?;
    m.add_function(wrap_pyfunction!(io::delete_directory, m)?)?;
    m.add_function(wrap_pyfunction!(io::get_file_mtime, m)?)?;
    m.add_function(wrap_pyfunction!(io::read_file_chunked, m)?)?;

    // Module metadata
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__author__", "Vadim Toptunov")?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_module_loads() {
        // Basic smoke test
        assert!(true);
    }
}
