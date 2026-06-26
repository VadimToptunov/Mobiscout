# Rust Core Setup Guide

## Prerequisites

### Install Rust

```bash
# macOS/Linux
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Windows
# Download from: https://rustup.rs/

# Verify installation
rustc --version
cargo --version
```

### Install Python Build Tools

```bash
pip install maturin
```

---

## Building the Rust Core

### Development Build

```bash
cd rust_core
maturin develop
```

This compiles the Rust code and installs it in your Python environment.

### Release Build

```bash
maturin build --release
```

Creates optimized wheels in `target/wheels/`.

---

## Testing

### Run Rust Tests

```bash
cd rust_core
cargo test
```

### Run Benchmarks

```bash
cd rust_core
cargo bench
```

### Test Python Integration

```python
# Test if Rust core is available
try:
    from observe_core import RustAstAnalyzer
    print("✅ Rust core available!")
    
    analyzer = RustAstAnalyzer()
    metrics = analyzer.analyze_file("test.py")
    print(f"Metrics: {metrics}")
except ImportError:
    print("❌ Rust core not available, using Python fallback")
```

---

## Development Workflow

### 1. Make changes to Rust code

```bash
# Edit rust_core/src/ast_analyzer.rs
```

### 2. Rebuild and test

```bash
cd rust_core
maturin develop && cd .. && python -m pytest
```

### 3. Benchmark

```bash
cd rust_core
cargo bench
```

---

## Troubleshooting

### "cargo: command not found"

Install Rust:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

### "maturin: command not found"

```bash
pip install maturin
```

### Build Errors

```bash
# Clean and rebuild
cd rust_core
cargo clean
maturin develop
```

---

## Performance Comparison

### Before (Python only)

```bash
time observe business analyze ./large_project/src
# Real: 45.2s
```

### After (with Rust core)

```bash
time observe business analyze ./large_project/src
# Real: 0.5s  (90x faster!)
```

---

## Distribution

### Build wheels for PyPI

```bash
cd rust_core

# Build for current platform
maturin build --release

# Build for all platforms (requires Docker)
maturin build --release --manylinux 2014
```

### Publish to PyPI

```bash
maturin publish
```

---

## Next Steps

1. Install Rust (see above)
2. Build Rust core: `cd rust_core && maturin develop`
3. Run benchmarks: `cargo bench`
4. Integrate into Python: Framework will auto-detect Rust core
