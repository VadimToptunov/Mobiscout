//! Fast multi-pattern line scanner for SAST.
//!
//! The Python SAST analyzers run one `re.search` per rule per line — tens of thousands of
//! regex searches over a modest repo. This does the same work the way a native scanner
//! should: compile every rule into a single `RegexSet` (one DFA), match ALL rules against a
//! line in one pass, and run files in parallel (GIL released). The semantic logic
//! (metadata, comment-skipping, taint dataflow) stays in Python; only the CPU-hot matching
//! moves here.

use pyo3::prelude::*;
use rayon::prelude::*;
use regex::RegexSet;

/// Scan `lines_per_file` for `patterns`, returning one tuple per (line, matching-rule):
/// `(file_index, line_number_1based, rule_index)`.
///
/// The caller splits each file into its lines (Python `str.splitlines()`) and passes the
/// lists — the scanner never splits, so its line numbers match the caller's exactly. (An
/// earlier version took whole file texts and split with `str::lines()`, which disagreed
/// with Python's `splitlines()` on form-feed / U+2028 and mis-numbered findings.)
///
/// `ignore_case` applies the case-insensitive flag to every rule. A rule that fails to
/// compile makes the whole call raise `ValueError` (the caller passes known-good patterns).
#[pyfunction]
#[pyo3(signature = (lines_per_file, patterns, ignore_case = false))]
pub fn scan_lines(
    py: Python,
    lines_per_file: Vec<Vec<String>>,
    patterns: Vec<String>,
    ignore_case: bool,
) -> PyResult<Vec<(usize, usize, usize)>> {
    let built: Vec<String> = if ignore_case {
        patterns.iter().map(|p| format!("(?i){}", p)).collect()
    } else {
        patterns
    };
    let set = RegexSet::new(&built)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("bad rule pattern: {e}")))?;

    // Release the GIL: the scan is pure Rust over owned data, so files run in parallel.
    let results = py.allow_threads(|| {
        lines_per_file
            .par_iter()
            .enumerate()
            .flat_map_iter(|(file_idx, lines)| {
                let set = &set;
                lines.iter().enumerate().flat_map(move |(line_idx, line)| {
                    set.matches(line)
                        .into_iter()
                        .map(move |rule_idx| (file_idx, line_idx + 1, rule_idx))
                        .collect::<Vec<_>>()
                })
            })
            .collect::<Vec<_>>()
    });
    Ok(results)
}
