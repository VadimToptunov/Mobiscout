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

/// Scan `contents` (already-read file texts) for `patterns`, returning one tuple per
/// (line, matching-rule): `(file_index, line_number_1based, rule_index, line_text)`.
///
/// `ignore_case` applies the case-insensitive flag to every rule. A rule that fails to
/// compile makes the whole call raise `ValueError` (the caller passes known-good patterns).
#[pyfunction]
#[pyo3(signature = (contents, patterns, ignore_case = false))]
pub fn scan_lines(
    py: Python,
    contents: Vec<String>,
    patterns: Vec<String>,
    ignore_case: bool,
) -> PyResult<Vec<(usize, usize, usize, String)>> {
    let built: Vec<String> = if ignore_case {
        patterns.iter().map(|p| format!("(?i){}", p)).collect()
    } else {
        patterns
    };
    let set = RegexSet::new(&built)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("bad rule pattern: {e}")))?;

    // Release the GIL: the scan is pure Rust over owned data, so files run in parallel.
    let results = py.allow_threads(|| {
        contents
            .par_iter()
            .enumerate()
            .flat_map_iter(|(file_idx, content)| {
                let set = &set;
                content
                    .lines()
                    .enumerate()
                    .flat_map(move |(line_idx, line)| {
                        let hits = set.matches(line);
                        hits.into_iter()
                            .map(move |rule_idx| (file_idx, line_idx + 1, rule_idx, line.to_string()))
                            .collect::<Vec<_>>()
                    })
            })
            .collect::<Vec<_>>()
    });
    Ok(results)
}
