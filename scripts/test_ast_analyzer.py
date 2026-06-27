"""
Simple test for AST Analyzer
"""

from pathlib import Path

from framework.analyzers.ast_analyzer import ASTAnalyzer


def test_ast_analyzer() -> None:
    """Test AST analyzer on framework code"""
    analyzer = ASTAnalyzer(Path("framework/analyzers"))
    result = analyzer.analyze_python()

    print("\n✅ AST Analysis Test Results:")
    print(f"   Total Functions: {result['summary']['total_functions']}")
    print("   High Complexity: " f"{result['summary']['high_complexity_functions']}")
    print("   Average Complexity: " f"{result['summary']['average_complexity']:.2f}")

    # Show most complex
    if result["functions"]:
        most_complex = max(result["functions"], key=lambda f: f["cyclomatic_complexity"])
        print(f"\n   Most complex function: {most_complex['name']}")
        print("   Cyclomatic Complexity: " f"{most_complex['cyclomatic_complexity']}")
        print("   Cognitive Complexity: " f"{most_complex['cognitive_complexity']}")
        print(f"   Nested Depth: {most_complex['nested_depth']}")

    assert result["summary"]["total_functions"] > 0, "Should find functions"
    print("\n✅ Test passed!")


if __name__ == "__main__":
    test_ast_analyzer()
