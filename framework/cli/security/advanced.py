"""
Advanced Security CLI Commands

Advanced security analysis commands: secrets, pinning, binary, privacy, rootcheck, code, full, owasp.
"""

from pathlib import Path
from typing import Optional
import json

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.advanced_security import (
    AdvancedSecurityScanner,
    HardcodedSecretsScanner,
    CertificatePinningAnalyzer,
    BinarySecurityAnalyzer,
    PrivacyComplianceChecker,
    RootJailbreakAnalyzer,
    SecureCodingAnalyzer,
    RiskLevel,
)
from framework.cli.security.base import (
    security,
    console,
    validate_path,
    get_risk_style,
    create_progress_context,
)


@security.command()
@click.argument("source_path", type=Path)
@click.option("--output", "-o", type=Path, help="Output report path")
@click.option("--format", "-f", type=click.Choice(["json", "sarif", "html"]), default="json", help="Report format")
def secrets(source_path: Path, output: Optional[Path], format: str) -> None:
    """
    Scan for hardcoded secrets in source code.

    Uses GitHub-level pattern detection with entropy analysis.

    Example:
        observe security secrets ./src
        observe security secrets ./project -o secrets_report.json
        observe security secrets ./app --format sarif
    """
    if not validate_path(source_path):
        raise SystemExit(1)

    console.print(Panel.fit("Hardcoded Secrets Scanner", style="bold red"))
    console.print(f"Scanning: {source_path}\n")

    scanner = HardcodedSecretsScanner()

    with create_progress_context() as progress:
        task = progress.add_task("Scanning for secrets...", total=None)
        findings = scanner.scan_directory(source_path)
        progress.update(task, completed=True)

    if not findings:
        console.print("[green]✓[/green] No hardcoded secrets found!")
        raise SystemExit(0)

    console.print(f"\n[red]Found {len(findings)} potential secret(s)[/red]\n")

    for finding in findings[:20]:
        risk_style = get_risk_style(finding.risk_level)

        panel = Panel(
            f"[bold]{finding.title}[/bold]\n\n"
            f"[dim]File:[/dim] {finding.file_path}:{finding.line_number}\n"
            f"[dim]Secret Type:[/dim] {finding.metadata.get('secret_type', 'Unknown')}\n"
            f"[dim]Entropy:[/dim] {finding.metadata.get('entropy', 0):.2f}\n\n"
            f"[cyan]Evidence:[/cyan] {finding.evidence[:100]}...\n\n"
            f"[yellow]Recommendation:[/yellow] {finding.recommendation}",
            title=f"[{risk_style}]{finding.risk_level.value.upper()}[/{risk_style}]",
            border_style=risk_style.split()[0],
        )
        console.print(panel)
        console.print()

    if len(findings) > 20:
        console.print(f"[dim]... and {len(findings) - 20} more findings[/dim]")

    if output:
        if format == "sarif":
            scanner.export_sarif(findings, output)
        else:
            data = [f.to_dict() for f in findings]
            with open(output, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    raise SystemExit(1 if findings else 0)


@security.command()
@click.argument("app_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True)
def pinning(app_path: Path, platform: str) -> None:
    """
    Analyze certificate pinning implementation.

    Checks for proper SSL/TLS pinning configuration.

    Example:
        observe security pinning app.apk --platform android
        observe security pinning app.ipa --platform ios
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    console.print(Panel.fit("Certificate Pinning Analysis", style="bold cyan"))

    analyzer = CertificatePinningAnalyzer()

    with console.status("[cyan]Analyzing certificate pinning..."):
        findings = analyzer.analyze(app_path, platform)

    if not findings:
        console.print("[green]✓[/green] Certificate pinning properly configured!")
        raise SystemExit(0)

    console.print(f"\n[yellow]Found {len(findings)} pinning issue(s)[/yellow]\n")

    for finding in findings:
        console.print(f"[red]•[/red] {finding.title}")
        console.print(f"  {finding.description}")
        console.print(f"  [dim]Recommendation:[/dim] {finding.recommendation}")
        console.print()

    raise SystemExit(1)


@security.command()
@click.argument("binary_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True)
def binary(binary_path: Path, platform: str) -> None:
    """
    Analyze binary security features.

    Checks for PIE, stack canaries, debuggable flags, etc.

    Example:
        observe security binary app.apk --platform android
        observe security binary app.ipa --platform ios
    """
    if not validate_path(binary_path):
        raise SystemExit(1)

    console.print(Panel.fit("Binary Security Analysis", style="bold magenta"))

    analyzer = BinarySecurityAnalyzer()

    with console.status("[cyan]Analyzing binary security..."):
        findings = analyzer.analyze(binary_path, platform)

    if not findings:
        console.print("[green]✓[/green] Binary security checks passed!")
        raise SystemExit(0)

    critical = [f for f in findings if f.risk_level == RiskLevel.CRITICAL]
    high = [f for f in findings if f.risk_level == RiskLevel.HIGH]
    medium = [f for f in findings if f.risk_level == RiskLevel.MEDIUM]
    low = [f for f in findings if f.risk_level == RiskLevel.LOW]

    console.print()
    table = Table(title="Binary Security Findings")
    table.add_column("Risk", style="bold", width=10)
    table.add_column("Finding", style="white")
    table.add_column("Recommendation", style="cyan")

    for finding in critical:
        table.add_row("[red]CRITICAL[/red]", finding.title, finding.recommendation[:50])
    for finding in high:
        table.add_row("[yellow]HIGH[/yellow]", finding.title, finding.recommendation[:50])
    for finding in medium:
        table.add_row("[blue]MEDIUM[/blue]", finding.title, finding.recommendation[:50])
    for finding in low:
        table.add_row("[dim]LOW[/dim]", finding.title, finding.recommendation[:50])

    console.print(table)

    if critical:
        raise SystemExit(2)
    elif high:
        raise SystemExit(1)
    raise SystemExit(0)


@security.command()
@click.argument("source_path", type=Path)
@click.option("--regulation", "-r", type=click.Choice(["gdpr", "ccpa", "all"]), default="all")
@click.option("--output", "-o", type=Path, help="Output report path")
def privacy(source_path: Path, regulation: str, output: Optional[Path]) -> None:
    """
    Check privacy compliance (GDPR, CCPA).

    Analyzes code for privacy-related issues.

    Example:
        observe security privacy ./src --regulation gdpr
        observe security privacy ./app -r all -o privacy_report.json
    """
    if not validate_path(source_path):
        raise SystemExit(1)

    console.print(Panel.fit("Privacy Compliance Check", style="bold blue"))
    console.print(f"Regulation: {regulation.upper()}\n")

    checker = PrivacyComplianceChecker()

    with console.status("[cyan]Analyzing privacy compliance..."):
        findings = checker.check_compliance(source_path, regulation)

    if not findings:
        console.print(f"[green]✓[/green] No {regulation.upper()} compliance issues found!")
        raise SystemExit(0)

    console.print(f"\n[yellow]Found {len(findings)} privacy issue(s)[/yellow]\n")

    for finding in findings:
        risk_style = "red" if finding.risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH] else "yellow"

        console.print(f"[{risk_style}]•[/{risk_style}] [{risk_style}]{finding.title}[/{risk_style}]")
        console.print(f"  [dim]File:[/dim] {finding.file_path}:{finding.line_number}")
        console.print(f"  {finding.description}")
        console.print(f"  [cyan]Recommendation:[/cyan] {finding.recommendation}")
        console.print()

    if output:
        data = [f.to_dict() for f in findings]
        with open(output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    raise SystemExit(1)


@security.command()
@click.argument("source_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios", "all"]), default="all")
def rootcheck(source_path: Path, platform: str) -> None:
    """
    Analyze root/jailbreak detection implementation.

    Checks for proper detection mechanisms.

    Example:
        observe security rootcheck ./src --platform android
        observe security rootcheck ./app -p ios
    """
    if not validate_path(source_path):
        raise SystemExit(1)

    console.print(Panel.fit("Root/Jailbreak Detection Analysis", style="bold yellow"))

    analyzer = RootJailbreakAnalyzer()

    with console.status("[cyan]Analyzing detection mechanisms..."):
        findings = analyzer.analyze(source_path, platform)

    if not findings:
        console.print("[green]✓[/green] Robust root/jailbreak detection in place!")
        raise SystemExit(0)

    console.print(f"\n[yellow]Found {len(findings)} detection gap(s)[/yellow]\n")

    for finding in findings:
        console.print(f"[yellow]•[/yellow] {finding.title}")
        console.print(f"  {finding.description}")
        console.print(f"  [cyan]Recommendation:[/cyan] {finding.recommendation}")
        console.print()

    raise SystemExit(1)


@security.command()
@click.argument("source_path", type=Path)
@click.option("--language", "-l", type=click.Choice(["python", "kotlin", "swift", "java", "all"]), default="all")
@click.option("--output", "-o", type=Path, help="Output report path")
def code(source_path: Path, language: str, output: Optional[Path]) -> None:
    """
    Analyze secure coding practices.

    Checks for common vulnerabilities like SQL injection, XSS, etc.

    Example:
        observe security code ./src --language python
        observe security code ./app -l all -o code_report.json
    """
    if not validate_path(source_path):
        raise SystemExit(1)

    console.print(Panel.fit("Secure Coding Analysis", style="bold cyan"))
    console.print(f"Language: {language.upper()}\n")

    analyzer = SecureCodingAnalyzer()

    with console.status("[cyan]Analyzing code security..."):
        findings = analyzer.analyze(source_path, language)

    if not findings:
        console.print("[green]✓[/green] No secure coding issues found!")
        raise SystemExit(0)

    by_category = {}
    for finding in findings:
        cat = finding.owasp_category.value if finding.owasp_category else "Other"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(finding)

    console.print(f"\n[red]Found {len(findings)} issue(s)[/red]\n")

    for category, cat_findings in by_category.items():
        console.print(f"\n[bold]{category}[/bold] ({len(cat_findings)} issues)")

        for finding in cat_findings[:5]:
            risk_style = "red" if finding.risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH] else "yellow"
            console.print(f"  [{risk_style}]•[/{risk_style}] {finding.title}")
            console.print(f"    [dim]{finding.file_path}:{finding.line_number}[/dim]")

        if len(cat_findings) > 5:
            console.print(f"    [dim]... and {len(cat_findings) - 5} more[/dim]")

    if output:
        data = [f.to_dict() for f in findings]
        with open(output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    critical_count = len([f for f in findings if f.risk_level == RiskLevel.CRITICAL])
    if critical_count > 0:
        raise SystemExit(2)
    raise SystemExit(1)


@security.command()
@click.argument("app_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True)
@click.option("--app-name", "-n", required=True, help="Application name")
@click.option("--output", "-o", type=Path, help="Output directory for reports")
@click.option("--format", "-f", type=click.Choice(["json", "sarif", "html"]), default="json")
def full(
    app_path: Path,
    platform: str,
    app_name: str,
    output: Optional[Path],
    format: str,
) -> None:
    """
    Run comprehensive security analysis.

    Combines all security checks into one comprehensive scan.

    Example:
        observe security full app.apk -p android -n MyApp -o ./reports
        observe security full app.ipa -p ios -n MyApp --format html
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    console.print(Panel.fit(
        f"Comprehensive Security Analysis\n\n"
        f"App: {app_name}\n"
        f"Platform: {platform.upper()}",
        style="bold red"
    ))

    scanner = AdvancedSecurityScanner()

    with create_progress_context() as progress:
        task = progress.add_task("Running full security scan...", total=None)
        result = scanner.full_scan(app_path, platform, app_name)
        progress.update(task, completed=True)

    console.print()
    console.print(Panel.fit("Security Scan Summary", style="bold green"))

    summary_table = Table()
    summary_table.add_column("Category", style="cyan")
    summary_table.add_column("Critical", style="red", justify="right")
    summary_table.add_column("High", style="yellow", justify="right")
    summary_table.add_column("Medium", style="blue", justify="right")
    summary_table.add_column("Low", style="dim", justify="right")

    categories = {}
    for finding in result.findings:
        cat = finding.owasp_category.value if finding.owasp_category else "Other"
        if cat not in categories:
            categories[cat] = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        if finding.risk_level == RiskLevel.CRITICAL:
            categories[cat]["critical"] += 1
        elif finding.risk_level == RiskLevel.HIGH:
            categories[cat]["high"] += 1
        elif finding.risk_level == RiskLevel.MEDIUM:
            categories[cat]["medium"] += 1
        elif finding.risk_level == RiskLevel.LOW:
            categories[cat]["low"] += 1

    for cat, counts in sorted(categories.items()):
        summary_table.add_row(
            cat[:30],
            str(counts["critical"]) if counts["critical"] else "-",
            str(counts["high"]) if counts["high"] else "-",
            str(counts["medium"]) if counts["medium"] else "-",
            str(counts["low"]) if counts["low"] else "-",
        )

    console.print(summary_table)

    total = len(result.findings)
    critical = len([f for f in result.findings if f.risk_level == RiskLevel.CRITICAL])
    high = len([f for f in result.findings if f.risk_level == RiskLevel.HIGH])

    console.print(f"\n[bold]Total Findings:[/bold] {total}")
    console.print(f"[red]Critical:[/red] {critical} | [yellow]High:[/yellow] {high}")

    if critical > 0:
        console.print("\n[red bold]CRITICAL RISK - Immediate action required![/red bold]")
    elif high > 0:
        console.print("\n[yellow bold]HIGH RISK - Action recommended[/yellow bold]")
    elif total > 0:
        console.print("\n[blue]MODERATE RISK - Review recommended[/blue]")
    else:
        console.print("\n[green]LOW RISK - No significant issues found[/green]")

    if output:
        output.mkdir(parents=True, exist_ok=True)

        if format == "sarif":
            sarif_path = output / f"{app_name}_security.sarif"
            scanner.export_sarif(result.findings, sarif_path)
            console.print(f"\n[green]✓[/green] SARIF report: {sarif_path}")
        elif format == "html":
            html_path = output / f"{app_name}_security.html"
            scanner.export_html(result, html_path)
            console.print(f"\n[green]✓[/green] HTML report: {html_path}")
        else:
            json_path = output / f"{app_name}_security.json"
            with open(json_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
            console.print(f"\n[green]✓[/green] JSON report: {json_path}")

    if critical > 0:
        raise SystemExit(2)
    elif high > 0:
        raise SystemExit(1)
    raise SystemExit(0)


@security.command()
def owasp() -> None:
    """
    Display OWASP Mobile Top 10 2024 categories.

    Example:
        observe security owasp
    """
    console.print(Panel.fit("OWASP Mobile Top 10 (2024)", style="bold cyan"))

    table = Table()
    table.add_column("ID", style="cyan", width=4)
    table.add_column("Category", style="bold")
    table.add_column("Description", style="white")

    owasp_items = [
        ("M1", "Improper Credential Usage", "Hardcoded credentials, insecure storage of secrets"),
        ("M2", "Inadequate Supply Chain Security", "Third-party dependencies, SDK vulnerabilities"),
        ("M3", "Insecure Authentication/Authorization", "Weak auth, broken access control"),
        ("M4", "Insufficient Input/Output Validation", "Injection attacks, XSS, path traversal"),
        ("M5", "Insecure Communication", "Cleartext traffic, weak TLS, missing cert pinning"),
        ("M6", "Inadequate Privacy Controls", "PII exposure, tracking, data minimization"),
        ("M7", "Insufficient Binary Protections", "Missing obfuscation, debuggable, no tamper detection"),
        ("M8", "Security Misconfiguration", "Debug enabled, weak permissions, exposed components"),
        ("M9", "Insecure Data Storage", "Unencrypted databases, logs with sensitive data"),
        ("M10", "Insufficient Cryptography", "Weak algorithms, hardcoded keys, improper implementation"),
    ]

    for id_, name, desc in owasp_items:
        table.add_row(id_, name, desc)

    console.print(table)

    console.print("\n[dim]Run 'observe security full' for comprehensive OWASP coverage[/dim]")
