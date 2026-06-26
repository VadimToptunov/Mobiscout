//! Fast AST Analysis Engine using tree-sitter
//!
//! Provides high-performance AST parsing and complexity metric calculation
//! for multiple programming languages commonly used in mobile development.
//!
//! Supported languages:
//! - Python
//! - Java
//! - Kotlin
//! - Swift
//! - JavaScript/TypeScript

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;
use std::path::Path;
use rayon::prelude::*;
use walkdir::WalkDir;
use anyhow::Result as AnyhowResult;
use log::{debug, warn, info};

/// Supported programming languages for AST analysis
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Language {
    Python,
    Java,
    Kotlin,
    Swift,
    JavaScript,
    TypeScript,
}

impl Language {
    /// Get language from file extension
    pub fn from_extension(ext: &str) -> Option<Self> {
        match ext.to_lowercase().as_str() {
            "py" => Some(Language::Python),
            "java" => Some(Language::Java),
            "kt" | "kts" => Some(Language::Kotlin),
            "swift" => Some(Language::Swift),
            "js" | "jsx" => Some(Language::JavaScript),
            "ts" | "tsx" => Some(Language::TypeScript),
            _ => None,
        }
    }

    /// Get tree-sitter language
    fn get_ts_language(&self) -> tree_sitter::Language {
        match self {
            Language::Python => tree_sitter_python::language(),
            Language::Java => tree_sitter_java::language(),
            Language::Kotlin => tree_sitter_kotlin::language(),
            Language::Swift => tree_sitter_swift::language(),
            Language::JavaScript => tree_sitter_javascript::language(),
            Language::TypeScript => tree_sitter_typescript::language_typescript(),
        }
    }

    /// Get control flow node types for this language
    fn control_flow_types(&self) -> &[&str] {
        match self {
            Language::Python => &[
                "if_statement", "for_statement", "while_statement",
                "try_statement", "with_statement", "match_statement",
                "elif_clause", "except_clause", "case_clause",
            ],
            Language::Java | Language::Kotlin => &[
                "if_statement", "for_statement", "while_statement",
                "do_statement", "try_statement", "switch_expression",
                "catch_clause", "when_entry",
            ],
            Language::Swift => &[
                "if_statement", "for_statement", "while_statement",
                "repeat_while_statement", "switch_statement",
                "guard_statement", "do_statement", "catch_clause",
            ],
            Language::JavaScript | Language::TypeScript => &[
                "if_statement", "for_statement", "while_statement",
                "do_statement", "try_statement", "switch_statement",
                "catch_clause", "ternary_expression",
            ],
        }
    }

    /// Get function definition node types for this language
    fn function_types(&self) -> &[&str] {
        match self {
            Language::Python => &["function_definition", "async_function_definition"],
            Language::Java => &["method_declaration", "constructor_declaration"],
            Language::Kotlin => &["function_declaration", "anonymous_function"],
            Language::Swift => &["function_declaration", "initializer_declaration"],
            Language::JavaScript | Language::TypeScript => &[
                "function_declaration", "function_expression",
                "arrow_function", "method_definition",
            ],
        }
    }

    /// Get class definition node types for this language
    fn class_types(&self) -> &[&str] {
        match self {
            Language::Python => &["class_definition"],
            Language::Java => &["class_declaration", "interface_declaration", "enum_declaration"],
            Language::Kotlin => &["class_declaration", "object_declaration", "interface_declaration"],
            Language::Swift => &["class_declaration", "struct_declaration", "protocol_declaration"],
            Language::JavaScript | Language::TypeScript => &[
                "class_declaration", "class_expression",
            ],
        }
    }
}

/// Complexity metrics for a code element
#[derive(Debug, Clone, Default)]
#[pyclass]
pub struct ComplexityMetrics {
    #[pyo3(get)]
    pub cyclomatic_complexity: usize,
    #[pyo3(get)]
    pub cognitive_complexity: usize,
    #[pyo3(get)]
    pub max_nesting_depth: usize,
    #[pyo3(get)]
    pub lines_of_code: usize,
    #[pyo3(get)]
    pub function_count: usize,
    #[pyo3(get)]
    pub class_count: usize,
}

#[pymethods]
impl ComplexityMetrics {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    fn __repr__(&self) -> String {
        format!(
            "ComplexityMetrics(cyclomatic={}, cognitive={}, nesting={}, loc={}, functions={}, classes={})",
            self.cyclomatic_complexity,
            self.cognitive_complexity,
            self.max_nesting_depth,
            self.lines_of_code,
            self.function_count,
            self.class_count,
        )
    }

    /// Get a risk assessment based on complexity
    fn risk_level(&self) -> &str {
        if self.cyclomatic_complexity > 20 || self.cognitive_complexity > 30 {
            "high"
        } else if self.cyclomatic_complexity > 10 || self.cognitive_complexity > 15 {
            "medium"
        } else {
            "low"
        }
    }
}

/// High-performance AST analyzer using tree-sitter
#[pyclass]
pub struct RustAstAnalyzer {
    cache: HashMap<String, ComplexityMetrics>,
    parsers: HashMap<String, tree_sitter::Parser>,
}

#[pymethods]
impl RustAstAnalyzer {
    #[new]
    fn new() -> Self {
        Self {
            cache: HashMap::new(),
            parsers: HashMap::new(),
        }
    }

    /// Analyze a single file
    #[pyo3(signature = (file_path))]
    fn analyze_file(&mut self, file_path: String) -> PyResult<ComplexityMetrics> {
        // Check cache
        if let Some(metrics) = self.cache.get(&file_path) {
            return Ok(metrics.clone());
        }

        // Determine language from extension
        let path = Path::new(&file_path);
        let ext = path.extension()
            .and_then(|e| e.to_str())
            .unwrap_or("");

        let language = Language::from_extension(ext)
            .ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(
                    format!("Unsupported file extension: {}", ext)
                )
            })?;

        // Read file
        let content = std::fs::read_to_string(&file_path)
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

        // Analyze
        let metrics = self.analyze_source_with_language(&content, language)?;

        // Cache result
        self.cache.insert(file_path, metrics.clone());

        Ok(metrics)
    }

    /// Analyze source code with explicit language
    #[pyo3(signature = (source, language))]
    fn analyze_source(&mut self, source: &str, language: &str) -> PyResult<ComplexityMetrics> {
        let lang = match language.to_lowercase().as_str() {
            "python" | "py" => Language::Python,
            "java" => Language::Java,
            "kotlin" | "kt" => Language::Kotlin,
            "swift" => Language::Swift,
            "javascript" | "js" => Language::JavaScript,
            "typescript" | "ts" => Language::TypeScript,
            _ => return Err(pyo3::exceptions::PyValueError::new_err(
                format!("Unsupported language: {}", language)
            )),
        };

        self.analyze_source_with_language(source, lang)
    }

    /// Analyze entire directory in parallel
    #[pyo3(signature = (directory_path, extensions = None))]
    fn analyze_directory(
        &mut self,
        py: Python,
        directory_path: String,
        extensions: Option<Vec<String>>,
    ) -> PyResult<PyObject> {
        let default_exts = vec![
            "py".to_string(), "java".to_string(), "kt".to_string(),
            "swift".to_string(), "js".to_string(), "ts".to_string(),
        ];
        let exts = extensions.as_ref().unwrap_or(&default_exts);

        // Collect all files
        let files: Vec<_> = WalkDir::new(&directory_path)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_type().is_file())
            .filter(|e| {
                e.path()
                    .extension()
                    .and_then(|s| s.to_str())
                    .map(|ext| exts.iter().any(|e| e.eq_ignore_ascii_case(ext)))
                    .unwrap_or(false)
            })
            .map(|e| e.path().to_string_lossy().to_string())
            .collect();

        info!("Analyzing {} files with tree-sitter...", files.len());

        // Parallel processing with rayon
        let results: Vec<(String, ComplexityMetrics)> = files
            .par_iter()
            .filter_map(|file_path| {
                let path = Path::new(file_path);
                let ext = path.extension()?.to_str()?;
                let language = Language::from_extension(ext)?;

                let content = std::fs::read_to_string(file_path).ok()?;

                // Create a new parser for this thread
                let mut parser = tree_sitter::Parser::new();
                parser.set_language(&language.get_ts_language()).ok()?;

                let tree = parser.parse(&content, None)?;
                let metrics = Self::compute_metrics(&tree, &content, language);

                Some((file_path.clone(), metrics))
            })
            .collect();

        // Convert to Python dict
        let dict = PyDict::new(py);
        for (file, metrics) in results.iter() {
            let py_metrics = Py::new(py, metrics.clone())?;
            dict.set_item(file, py_metrics)?;
        }

        Ok(dict.into())
    }

    /// Clear analysis cache
    fn clear_cache(&mut self) {
        self.cache.clear();
    }

    /// Get cache size
    fn cache_size(&self) -> usize {
        self.cache.len()
    }

    /// Get supported languages
    #[staticmethod]
    fn supported_languages() -> Vec<&'static str> {
        vec!["python", "java", "kotlin", "swift", "javascript", "typescript"]
    }
}

impl RustAstAnalyzer {
    fn analyze_source_with_language(&mut self, source: &str, language: Language) -> PyResult<ComplexityMetrics> {
        // Get or create parser for this language
        let lang_key = format!("{:?}", language);
        let parser = self.parsers.entry(lang_key).or_insert_with(|| {
            let mut p = tree_sitter::Parser::new();
            p.set_language(&language.get_ts_language()).expect("Failed to set language");
            p
        });

        let tree = parser.parse(source, None)
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Failed to parse source"))?;

        Ok(Self::compute_metrics(&tree, source, language))
    }

    fn compute_metrics(tree: &tree_sitter::Tree, source: &str, language: Language) -> ComplexityMetrics {
        let root = tree.root_node();
        let control_flow_types = language.control_flow_types();
        let function_types = language.function_types();
        let class_types = language.class_types();

        let mut metrics = ComplexityMetrics {
            lines_of_code: source.lines().filter(|l| !l.trim().is_empty()).count(),
            cyclomatic_complexity: 1, // Base complexity
            ..Default::default()
        };

        // Walk the tree and compute metrics
        let mut cursor = root.walk();
        Self::analyze_node_recursive(
            &mut cursor,
            &mut metrics,
            control_flow_types,
            function_types,
            class_types,
            0,
        );

        metrics
    }

    fn analyze_node_recursive(
        cursor: &mut tree_sitter::TreeCursor,
        metrics: &mut ComplexityMetrics,
        control_flow_types: &[&str],
        function_types: &[&str],
        class_types: &[&str],
        depth: usize,
    ) {
        let node = cursor.node();
        let node_type = node.kind();

        // Check for control flow (adds to cyclomatic complexity)
        if control_flow_types.contains(&node_type) {
            metrics.cyclomatic_complexity += 1;
            // Cognitive complexity increases with nesting
            metrics.cognitive_complexity += 1 + depth;
        }

        // Check for functions
        if function_types.contains(&node_type) {
            metrics.function_count += 1;
        }

        // Check for classes
        if class_types.contains(&node_type) {
            metrics.class_count += 1;
        }

        // Update max nesting depth
        if depth > metrics.max_nesting_depth {
            metrics.max_nesting_depth = depth;
        }

        // Determine if this node increases nesting depth
        let increases_nesting = control_flow_types.contains(&node_type)
            || function_types.contains(&node_type)
            || class_types.contains(&node_type);

        let new_depth = if increases_nesting { depth + 1 } else { depth };

        // Recurse into children
        if cursor.goto_first_child() {
            loop {
                Self::analyze_node_recursive(
                    cursor,
                    metrics,
                    control_flow_types,
                    function_types,
                    class_types,
                    new_depth,
                );
                if !cursor.goto_next_sibling() {
                    break;
                }
            }
            cursor.goto_parent();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_python_simple_function() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
def simple_function():
    return 42
"#;
        let metrics = analyzer.analyze_source(source, "python").unwrap();
        assert_eq!(metrics.function_count, 1);
        assert_eq!(metrics.cyclomatic_complexity, 1);
    }

    #[test]
    fn test_python_complex_function() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
def complex_function(x):
    if x > 10:
        for i in range(x):
            if i % 2 == 0:
                print(i)
    else:
        return 0
"#;
        let metrics = analyzer.analyze_source(source, "python").unwrap();
        assert!(metrics.cyclomatic_complexity >= 4); // if + for + if + else
        assert!(metrics.max_nesting_depth >= 2);
    }

    #[test]
    fn test_python_class() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
class MyClass:
    def __init__(self):
        self.value = 0

    def get_value(self):
        return self.value
"#;
        let metrics = analyzer.analyze_source(source, "python").unwrap();
        assert_eq!(metrics.class_count, 1);
        assert_eq!(metrics.function_count, 2);
    }

    #[test]
    fn test_java_function() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
public class Example {
    public void process(int x) {
        if (x > 0) {
            System.out.println(x);
        }
    }
}
"#;
        let metrics = analyzer.analyze_source(source, "java").unwrap();
        assert_eq!(metrics.class_count, 1);
        assert_eq!(metrics.function_count, 1);
        assert!(metrics.cyclomatic_complexity >= 2);
    }

    #[test]
    fn test_kotlin_function() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
fun processData(items: List<String>) {
    for (item in items) {
        when {
            item.isEmpty() -> println("Empty")
            else -> println(item)
        }
    }
}
"#;
        let metrics = analyzer.analyze_source(source, "kotlin").unwrap();
        assert_eq!(metrics.function_count, 1);
        assert!(metrics.cyclomatic_complexity >= 2);
    }

    #[test]
    fn test_swift_function() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
func calculate(_ value: Int) -> Int {
    if value > 0 {
        return value * 2
    } else {
        return 0
    }
}
"#;
        let metrics = analyzer.analyze_source(source, "swift").unwrap();
        assert_eq!(metrics.function_count, 1);
        assert!(metrics.cyclomatic_complexity >= 2);
    }

    #[test]
    fn test_javascript_function() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
function processItems(items) {
    for (const item of items) {
        if (item.valid) {
            console.log(item);
        }
    }
}
"#;
        let metrics = analyzer.analyze_source(source, "javascript").unwrap();
        assert_eq!(metrics.function_count, 1);
        assert!(metrics.cyclomatic_complexity >= 3);
    }

    #[test]
    fn test_typescript_class() {
        let mut analyzer = RustAstAnalyzer::new();
        let source = r#"
class DataProcessor {
    private data: string[];

    constructor(data: string[]) {
        this.data = data;
    }

    process(): void {
        for (const item of this.data) {
            console.log(item);
        }
    }
}
"#;
        let metrics = analyzer.analyze_source(source, "typescript").unwrap();
        assert_eq!(metrics.class_count, 1);
        assert!(metrics.function_count >= 1);
    }

    #[test]
    fn test_risk_level() {
        let low_risk = ComplexityMetrics {
            cyclomatic_complexity: 5,
            cognitive_complexity: 8,
            ..Default::default()
        };
        assert_eq!(low_risk.risk_level(), "low");

        let medium_risk = ComplexityMetrics {
            cyclomatic_complexity: 15,
            cognitive_complexity: 20,
            ..Default::default()
        };
        assert_eq!(medium_risk.risk_level(), "medium");

        let high_risk = ComplexityMetrics {
            cyclomatic_complexity: 25,
            cognitive_complexity: 40,
            ..Default::default()
        };
        assert_eq!(high_risk.risk_level(), "high");
    }
}
