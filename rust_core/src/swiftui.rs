//! SwiftUI structure from the tree-sitter Swift AST (#317).
//!
//! What `IOSSourceAnalyzer` needs from a `.swift` file — the `View` structs (screens), the
//! views carrying `.accessibilityIdentifier` / `.accessibilityLabel` (elements), the
//! `NavigationLink` / `.sheet` / `.fullScreenCover` edges and the `WindowGroup` root —
//! read from the syntax tree instead of regexes. The tree is what makes it exact where the
//! regex path guesses: an identifier in a comment is not an element, an interpolated
//! identifier (`"row_\(id)"`) is not a static locator, and the element's type is the view
//! the modifier is attached to, not the nearest component name in the preceding text.
//!
//! Python assembles the `AnalysisResult` from this (`framework/analyzers/native.py`); the
//! regex path stays as the fallback when the core is absent or a file doesn't parse cleanly.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use tree_sitter::{Node, Parser};

/// A view carrying an accessibility identifier (`is_identifier`) or label.
#[derive(Debug, PartialEq)]
pub struct Element {
    pub value: String,
    pub is_identifier: bool,
    /// The view the modifier is attached to (`Button`, `NavigationLink`, `VStack`, ...).
    pub view: String,
    pub screen: Option<String>,
    pub line: usize,
}

/// A navigation edge: the screen it starts on, where it goes, the link's label text and
/// the link's accessibilityIdentifier (the tap target).
#[derive(Debug, PartialEq)]
pub struct Edge {
    pub from_screen: Option<String>,
    pub to_screen: String,
    pub label: Option<String>,
    pub trigger_tag: Option<String>,
    pub line: usize,
}

#[derive(Debug, Default)]
pub struct SwiftUi {
    pub entry_screen: Option<String>,
    pub screens: Vec<(String, usize)>,
    pub elements: Vec<Element>,
    pub links: Vec<Edge>,
    pub presented: Vec<Edge>,
    /// The tree has ERROR/MISSING nodes — Python then prefers the regex path for the file.
    pub has_error: bool,
}

/// Parse `source` and extract its SwiftUI structure (`None` only if tree-sitter fails).
pub fn extract(source: &str) -> Option<SwiftUi> {
    let mut parser = Parser::new();
    parser.set_language(&tree_sitter_swift::LANGUAGE.into()).ok()?;
    let tree = parser.parse(source, None)?;
    let mut out = SwiftUi {
        has_error: tree.root_node().has_error(),
        ..Default::default()
    };
    visit(tree.root_node(), source.as_bytes(), None, &mut out);
    Some(out)
}

fn visit(node: Node, src: &[u8], screen: Option<&str>, out: &mut SwiftUi) {
    let mut current = screen.map(str::to_owned);
    match node.kind() {
        "class_declaration" => {
            if let Some(name) = view_struct(node, src) {
                out.screens.push((text(name, src).to_owned(), line(name)));
                current = Some(text(name, src).to_owned());
            }
        }
        "call_expression" => on_call(node, src, current.as_deref(), out),
        _ => {}
    }
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        visit(child, src, current.as_deref(), out);
    }
}

/// The name node of a `struct X: ..., View` declaration, else `None`.
fn view_struct<'t>(node: Node<'t>, src: &[u8]) -> Option<Node<'t>> {
    let kind = node.child_by_field_name("declaration_kind")?;
    if text(kind, src) != "struct" {
        return None;
    }
    let mut cursor = node.walk();
    let is_view = node
        .named_children(&mut cursor)
        .filter(|c| c.kind() == "inheritance_specifier")
        .any(|c| text(c, src) == "View");
    if is_view {
        node.child_by_field_name("name")
    } else {
        None
    }
}

fn on_call(call: Node, src: &[u8], screen: Option<&str>, out: &mut SwiftUi) {
    let Some(callee) = call.named_child(0) else { return };
    match callee.kind() {
        "simple_identifier" => match text(callee, src) {
            "WindowGroup" if out.entry_screen.is_none() => {
                out.entry_screen = trailing_lambdas(call, src)
                    .first()
                    .and_then(|(_, lambda)| first_view(*lambda, src));
            }
            "NavigationLink" => {
                if let Some((to_screen, label)) = nav_link(call, src) {
                    out.links.push(Edge {
                        from_screen: screen.map(str::to_owned),
                        to_screen,
                        label,
                        trigger_tag: identifier_modifier(call, src),
                        line: line(callee),
                    });
                }
            }
            _ => {}
        },
        "navigation_expression" => {
            let Some(suffix) = callee.child_by_field_name("suffix") else { return };
            let modifier = suffix.child_by_field_name("suffix").map(|n| text(n, src)).unwrap_or("");
            match modifier {
                "accessibilityIdentifier" | "accessibilityLabel" => {
                    let value = string_args(call, src).into_iter().next().flatten();
                    let view = callee.child_by_field_name("target").and_then(|t| base_view(t, src));
                    if let (Some(value), Some(view)) = (value, view) {
                        out.elements.push(Element {
                            value,
                            is_identifier: modifier == "accessibilityIdentifier",
                            view,
                            screen: screen.map(str::to_owned),
                            line: line(suffix),
                        });
                    }
                }
                "sheet" | "fullScreenCover" => {
                    let presented = trailing_lambdas(call, src)
                        .first()
                        .and_then(|(_, lambda)| first_view(*lambda, src));
                    if let Some(to_screen) = presented {
                        out.presented.push(Edge {
                            from_screen: screen.map(str::to_owned),
                            to_screen,
                            label: None,
                            trigger_tag: None,
                            line: line(suffix),
                        });
                    }
                }
                _ => {}
            }
        }
        _ => {}
    }
}

/// (destination view, label text) of a NavigationLink in any of its forms:
/// `(destination: X()) { label }`, `("Label", destination: X())`, `{ X() } label: { label }`
/// and `("Label") { X() }`. `None` for the value-based `NavigationLink(value:)`, whose
/// destination lives in a separate `.navigationDestination`.
fn nav_link(call: Node, src: &[u8]) -> Option<(String, Option<String>)> {
    let args = value_arguments(call);
    let lambdas = trailing_lambdas(call, src);
    let title = || string_args(call, src).into_iter().flatten().next();
    let unlabeled = lambdas.iter().find(|(name, _)| name.is_none()).map(|(_, l)| *l);
    if let Some(dest) = args.iter().find(|a| arg_label(**a, src) == Some("destination")) {
        let value = dest.child_by_field_name("value")?;
        let to = if value.kind() == "lambda_literal" { first_view(value, src) } else { base_view(value, src) }?;
        return Some((to, title().or_else(|| unlabeled.and_then(|l| first_text(l, src)))));
    }
    // Without `destination:`, the parentheses may hold only the title string.
    if args.iter().any(|a| arg_label(*a, src).is_some()) || args.len() > 1 {
        return None;
    }
    let to = first_view(unlabeled?, src)?;
    let label_lambda = lambdas.iter().find(|(name, _)| *name == Some("label")).map(|(_, l)| *l);
    Some((to, title().or_else(|| label_lambda.and_then(|l| first_text(l, src)))))
}

/// The accessibilityIdentifier in the modifier chain applied to `view` (`.a().b("id")`).
fn identifier_modifier(view: Node, src: &[u8]) -> Option<String> {
    let mut node = view;
    loop {
        let nav = node.parent()?;
        if nav.kind() != "navigation_expression" || nav.child_by_field_name("target") != Some(node) {
            return None;
        }
        let call = nav.parent().filter(|p| p.kind() == "call_expression")?;
        let modifier = nav.child_by_field_name("suffix")?.child_by_field_name("suffix")?;
        if text(modifier, src) == "accessibilityIdentifier" {
            return string_args(call, src).into_iter().next().flatten();
        }
        node = call;
    }
}

/// The view at the root of a modifier chain: `Text("x").bold().padding()` → `Text`.
fn base_view(mut expr: Node, src: &[u8]) -> Option<String> {
    loop {
        match expr.kind() {
            "call_expression" => {
                let callee = expr.named_child(0)?;
                if callee.kind() == "simple_identifier" {
                    return Some(text(callee, src).to_owned());
                }
                expr = callee;
            }
            "navigation_expression" => expr = expr.child_by_field_name("target")?,
            _ => return None,
        }
    }
}

/// The view a closure builds first: `{ SettingsView() }` → `SettingsView`.
fn first_view(lambda: Node, src: &[u8]) -> Option<String> {
    let mut cursor = lambda.walk();
    let statements = lambda.named_children(&mut cursor).find(|c| c.kind() == "statements")?;
    base_view(statements.named_child(0)?, src)
}

/// The first `Text("...")` string inside `node` (a link's label closure).
fn first_text(node: Node, src: &[u8]) -> Option<String> {
    if node.kind() == "call_expression"
        && node.named_child(0).map(|c| c.kind() == "simple_identifier" && text(c, src) == "Text") == Some(true)
    {
        if let Some(Some(s)) = string_args(node, src).into_iter().next() {
            return Some(s);
        }
    }
    let mut cursor = node.walk();
    let children: Vec<Node> = node.named_children(&mut cursor).collect();
    children.into_iter().find_map(|c| first_text(c, src))
}

fn call_suffix(call: Node) -> Option<Node> {
    let mut cursor = call.walk();
    let found = call.named_children(&mut cursor).find(|c| c.kind() == "call_suffix");
    found
}

/// The `value_argument`s inside a call's parentheses.
fn value_arguments(call: Node) -> Vec<Node> {
    let Some(suffix) = call_suffix(call) else { return Vec::new() };
    let mut cursor = suffix.walk();
    let Some(args) = suffix.named_children(&mut cursor).find(|c| c.kind() == "value_arguments") else {
        return Vec::new();
    };
    let mut cursor = args.walk();
    let found: Vec<Node> = args.named_children(&mut cursor).filter(|c| c.kind() == "value_argument").collect();
    found
}

fn arg_label<'s>(arg: Node, src: &'s [u8]) -> Option<&'s str> {
    arg.child_by_field_name("name").map(|n| text(n, src))
}

/// Each unlabeled argument as its static string (`None` for a non-literal or interpolated one).
fn string_args(call: Node, src: &[u8]) -> Vec<Option<String>> {
    value_arguments(call)
        .into_iter()
        .filter(|a| arg_label(*a, src).is_none())
        .map(|a| a.child_by_field_name("value").and_then(|v| static_string(v, src)))
        .collect()
}

/// A plain, non-empty string literal's text; `None` when it interpolates or escapes, since
/// that is not a locator the device will ever show verbatim.
fn static_string(node: Node, src: &[u8]) -> Option<String> {
    if node.kind() != "line_string_literal" {
        return None;
    }
    let mut cursor = node.walk();
    let parts: Vec<Node> = node.named_children(&mut cursor).collect();
    if parts.is_empty() || parts.iter().any(|p| p.kind() != "line_str_text") {
        return None;
    }
    Some(parts.iter().map(|p| text(*p, src)).collect())
}

/// The trailing closures of a call with their labels: `{ a } label: { b }` →
/// `[(None, a), (Some("label"), b)]`.
fn trailing_lambdas<'t, 's>(call: Node<'t>, src: &'s [u8]) -> Vec<(Option<&'s str>, Node<'t>)> {
    let Some(suffix) = call_suffix(call) else { return Vec::new() };
    let mut out = Vec::new();
    let mut name = None;
    let mut cursor = suffix.walk();
    for child in suffix.named_children(&mut cursor) {
        match child.kind() {
            "simple_identifier" => name = Some(text(child, src)),
            "lambda_literal" => out.push((name.take(), child)),
            _ => {}
        }
    }
    out
}

fn text<'s>(node: Node, src: &'s [u8]) -> &'s str {
    node.utf8_text(src).unwrap_or("")
}

fn line(node: Node) -> usize {
    node.start_position().row + 1
}

fn edges(edges: Vec<Edge>) -> Vec<(Option<String>, String, Option<String>, Option<String>, usize)> {
    edges
        .into_iter()
        .map(|e| (e.from_screen, e.to_screen, e.label, e.trigger_tag, e.line))
        .collect()
}

/// `extract` for Python: a dict of `entry_screen`, `screens` [(name, line)], `elements`
/// [(value, is_identifier, view, screen, line)], `links` / `presented`
/// [(from_screen, to_screen, label, trigger_tag, line)] and `has_error`.
#[pyfunction]
pub fn extract_swiftui(py: Python<'_>, source: &str) -> PyResult<Py<PyAny>> {
    let x = extract(source)
        .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("tree-sitter could not parse the Swift source"))?;
    let elements: Vec<_> = x
        .elements
        .into_iter()
        .map(|e| (e.value, e.is_identifier, e.view, e.screen, e.line))
        .collect();
    let dict = PyDict::new(py);
    dict.set_item("entry_screen", x.entry_screen)?;
    dict.set_item("screens", x.screens)?;
    dict.set_item("elements", elements)?;
    dict.set_item("links", edges(x.links))?;
    dict.set_item("presented", edges(x.presented))?;
    dict.set_item("has_error", x.has_error)?;
    Ok(dict.into_any().unbind())
}

#[cfg(test)]
mod tests {
    use super::*;

    const APP: &str = include_str!("../../tests/fixtures/source_navigation/App.swift");

    fn edge(from: &str, to: &str, label: Option<&str>, tag: Option<&str>, line: usize) -> Edge {
        Edge {
            from_screen: Some(from.into()),
            to_screen: to.into(),
            label: label.map(Into::into),
            trigger_tag: tag.map(Into::into),
            line,
        }
    }

    #[test]
    fn navigation_fixture() {
        let x = extract(APP).unwrap();
        assert!(!x.has_error);
        assert_eq!(x.entry_screen.as_deref(), Some("HomeView"));
        let names: Vec<&str> = x.screens.iter().map(|(n, _)| n.as_str()).collect();
        assert_eq!(names, ["HomeView", "DetailsView", "ProfileView", "OrdersView", "SettingsView"]);
        assert_eq!(
            x.links,
            [
                edge("HomeView", "DetailsView", Some("Details"), Some("open_details"), 18),
                edge("HomeView", "ProfileView", Some("Profile"), None, 22),
                edge("HomeView", "OrdersView", Some("Orders"), None, 23),
            ]
        );
        assert_eq!(x.presented, [edge("HomeView", "SettingsView", None, None, 30)]);
    }

    #[test]
    fn element_is_the_view_the_modifier_is_on() {
        let x = extract(APP).unwrap();
        let open = x.elements.iter().find(|e| e.value == "open_details").unwrap();
        assert_eq!((open.view.as_str(), open.screen.as_deref(), open.line), ("NavigationLink", Some("HomeView"), 21));
        let close = extract(r#"struct A: View { var body: some View { Button { Image(systemName: "x") }.accessibilityIdentifier("close") } }"#).unwrap();
        assert_eq!(close.elements[0].view, "Button");
    }

    #[test]
    fn comments_and_interpolated_ids_are_not_elements() {
        let x = extract(
            r#"struct A: View {
                // Text("x").accessibilityIdentifier("old")
                var body: some View { Text("y").accessibilityIdentifier("row_\(id)") }
            }"#,
        )
        .unwrap();
        assert!(x.elements.is_empty());
    }

    #[test]
    fn title_with_destination_closure_and_value_links() {
        let x = extract(
            r#"struct A: View { var body: some View { VStack {
                NavigationLink("Help") { HelpView() }
                NavigationLink(value: item) { Text("Row") }
            } } }"#,
        )
        .unwrap();
        assert_eq!(x.links.len(), 1);
        assert_eq!((x.links[0].to_screen.as_str(), x.links[0].label.as_deref()), ("HelpView", Some("Help")));
    }
}
