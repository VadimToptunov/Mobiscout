"""
CLI Commands - Documentation generation
"""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from framework.documentation import DocGenerator, DocConfig, DocFormat

console = Console()


@click.group()
def docs() -> None:
    """Generate documentation from code"""
    pass


@docs.command()
@click.argument("source_dir", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="docs/api",
    help="Output directory for documentation"
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["markdown", "html", "json", "sphinx"]),
    default="markdown",
    help="Documentation format"
)
@click.option("--title", default="API Documentation", help="Documentation title")
@click.option("--include-private", is_flag=True, help="Include private members")
@click.option("--include-source", is_flag=True, help="Include source code")
@click.option("--no-toc", is_flag=True, help="Disable table of contents")
@click.option("--theme", default="default", help="Documentation theme")
def generate(
        source_dir: str,
        output: str,
        format: str,
        title: str,
        include_private: bool,
        include_source: bool,
        no_toc: bool,
        theme: str,
) -> None:
    """Generate documentation from source code"""
    console.print(Panel.fit("📚 Documentation Generator", style="bold cyan"))

    # Create config
    config = DocConfig(
        source_dir=Path(source_dir),
        output_dir=Path(output),
        format=DocFormat(format),
        title=title,
        include_private=include_private,
        include_source=include_source,
        include_toc=not no_toc,
        theme=theme,
    )

    # Display config
    console.print(f"Source: {source_dir}")
    console.print(f"Output: {output}")
    console.print(f"Format: {format}")
    console.print(f"Title: {title}")
    console.print()

    # Generate documentation
    generator = DocGenerator(config)

    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
    ) as progress:
        task = progress.add_task("Generating documentation...", total=None)
        generator.generate()

    # Success message
    console.print()
    console.print(Panel.fit("✅ Documentation generated successfully!", style="bold green"))
    console.print(f"\n📁 Output: {output}")

    if format == "html":
        console.print(f"🌐 Open: file://{Path(output).absolute()}/index.html")
    elif format == "markdown":
        console.print(f"📄 Index: {Path(output).absolute()}/index.md")


@docs.command()
@click.argument("source_dir", type=click.Path(exists=True))
def analyze(source_dir: str) -> None:
    """Analyze code structure"""
    from framework.documentation.parser import CodeParser
    from rich.table import Table

    console.print(Panel.fit("🔍 Code Analysis", style="bold cyan"))

    parser = CodeParser()
    source_path = Path(source_dir)

    python_files = list(source_path.rglob("*.py"))
    console.print(f"Found {len(python_files)} Python files\n")

    # Statistics
    total_classes = 0
    total_functions = 0
    total_lines = 0

    with console.status("[bold green]Analyzing code..."):
        for file_path in python_files:
            try:
                module = parser.parse_file(file_path)
                total_classes += len(module.classes)
                total_functions += len(module.functions)

                # Count lines
                with open(file_path) as f:
                    total_lines += len(f.readlines())
            except (OSError, SyntaxError, UnicodeDecodeError):
                pass

    # Display results
    table = Table(title="Code Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="yellow")

    table.add_row("Files", f"{len(python_files):,}")
    table.add_row("Classes", f"{total_classes:,}")
    table.add_row("Functions", f"{total_functions:,}")
    table.add_row("Lines of Code", f"{total_lines:,}")

    console.print(table)


@docs.command()
@click.argument("file_path", type=click.Path(exists=True))
def inspect(file_path: str) -> None:
    """Inspect a Python file"""
    from framework.documentation.parser import CodeParser
    from rich.table import Table

    console.print(Panel.fit(f"🔬 File Inspection: {file_path}", style="bold cyan"))

    parser = CodeParser()
    module = parser.parse_file(Path(file_path))

    # Module info
    console.print(f"\n[bold]Module:[/bold] {module.name}")
    if module.docstring:
        console.print(f"[bold]Description:[/bold] {module.docstring}\n")

    # Classes
    if module.classes:
        console.print(Panel.fit("📦 Classes", style="bold blue"))

        for cls in module.classes:
            console.print(f"\n[bold cyan]{cls.name}[/bold cyan]")

            if cls.bases:
                console.print(f"  Inherits: {', '.join(cls.bases)}")

            if cls.docstring:
                console.print(f"  {cls.docstring}")

            if cls.methods:
                methods_table = Table(title=f"{cls.name} Methods", show_header=True)
                methods_table.add_column("Method", style="cyan")
                methods_table.add_column("Signature", style="yellow")

                for method in cls.methods[:10]:  # Show first 10
                    methods_table.add_row(method.name, method.signature)

                console.print(methods_table)

    # Functions
    if module.functions:
        console.print(Panel.fit("⚙️ Functions", style="bold green"))

        functions_table = Table(show_header=True)
        functions_table.add_column("Function", style="cyan")
        functions_table.add_column("Signature", style="yellow")

        for func in module.functions:
            functions_table.add_row(func.name, func.signature)

        console.print(functions_table)


@docs.command()
@click.argument("source_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file")
def coverage(source_dir: str, output: str | None) -> None:
    """Check documentation coverage"""
    from framework.documentation.parser import CodeParser
    from rich.table import Table

    console.print(Panel.fit("📊 Documentation Coverage", style="bold cyan"))

    parser = CodeParser()
    source_path = Path(source_dir)

    python_files = list(source_path.rglob("*.py"))

    total_items = 0
    documented_items = 0
    coverage_by_file = []

    with console.status("[bold green]Analyzing coverage..."):
        for file_path in python_files:
            try:
                module = parser.parse_file(file_path)

                file_total = 0
                file_documented = 0

                # Module docstring
                file_total += 1
                if module.docstring:
                    file_documented += 1

                # Classes
                for cls in module.classes:
                    file_total += 1
                    if cls.docstring:
                        file_documented += 1

                    # Methods
                    for method in cls.methods:
                        file_total += 1
                        if method.docstring:
                            file_documented += 1

                # Functions
                for func in module.functions:
                    file_total += 1
                    if func.docstring:
                        file_documented += 1

                total_items += file_total
                documented_items += file_documented

                if file_total > 0:
                    file_coverage = (file_documented / file_total) * 100
                    coverage_by_file.append({
                        "file": str(file_path.relative_to(source_path)),
                        "coverage": file_coverage,
                        "documented": file_documented,
                        "total": file_total,
                    })

            except (OSError, SyntaxError, UnicodeDecodeError):
                pass

    # Overall coverage
    overall_coverage = (documented_items / total_items * 100) if total_items > 0 else 0

    console.print()
    console.print(f"[bold]Overall Coverage:[/bold] {overall_coverage:.1f}%")
    console.print(f"Documented: {documented_items}/{total_items}\n")

    # Top undocumented files
    undocumented = sorted(coverage_by_file, key=lambda x: x["coverage"])[:10]

    if undocumented:
        table = Table(title="Files Needing Documentation")
        table.add_column("File", style="cyan")
        table.add_column("Coverage", style="yellow")
        table.add_column("Documented/Total", style="green")

        for item in undocumented:
            coverage_style = "red" if item["coverage"] < 50 else "yellow" if item["coverage"] < 80 else "green"
            table.add_row(
                item["file"],
                f"[{coverage_style}]{item['coverage']:.1f}%[/{coverage_style}]",
                f"{item['documented']}/{item['total']}",
            )

        console.print(table)

    # Save report
    if output:
        import json
        report = {
            "overall_coverage": overall_coverage,
            "total_items": total_items,
            "documented_items": documented_items,
            "files": coverage_by_file,
        }

        with open(output, "w") as f:
            json.dump(report, f, indent=2)

        console.print(f"\n💾 Report saved to: {output}")
