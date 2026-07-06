# Mobile Test Recorder → JetBrains IDE Plugin: Complete Roadmap

## Vision

Transform `mobile-test-recorder` into a **professional JetBrains IDE plugin** that provides:

- **Interactive UI control** (tap, swipe, type, inspect) within the IDE
- **Multi-language support** (Python, Java, Kotlin, JS/TS, Go, Ruby)
- **Multi-backend automation** (Appium v1/v2, Espresso, XCTest, Detox, Maestro, Playwright)
- **Smart selectors** with AI-powered stability scoring and healing
- **Flow & state analysis** with invariant detection
- **Static code analysis** (when source available): security, API tracing, fuzzing
- **Local-first architecture** - no servers, no SaaS, pure desktop product
- **Monetization**: One-time purchase model for PRO and Enterprise features

---

## Architecture Overview

```
JetBrains IDE Plugin (Kotlin)
│
├── ToolWindow / Side Panels
│   ├── Device Management (Android/iOS)
│   ├── Emulator/Simulator Viewer
│   ├── Appium XML Inspector
│   ├── Device Logs (logcat/simctl)
│   ├── Selector Hints & Stability
│   ├── Flow Graph Visualization
│   └── Static Analysis Results
│
├── Interactive UI Control
│   ├── Screenshot/Video Stream
│   ├── Element Overlay
│   └── Actions: Tap / Swipe / Type / Rotate / Inspect
│
├── LSP Client / DSL Support
│   ├── Smart Autocomplete (flow-aware)
│   ├── Go-to-Screen Navigation
│   └── Inline Diagnostics
│
└── Protocol Layer (JSON-RPC / gRPC)
     │
     └── mobile-test-recorder CLI (Backend)
         ├── Core Engine (Rust)
         │   ├── AST Analysis
         │   ├── Event Correlation
         │   ├── Business Logic Detection
         │   └── File I/O
         │
         ├── Python ML Layer
         │   ├── Element Classification
         │   ├── Self-Learning
         │   └── Selector Stability Scoring
         │
         ├── Recorder & Selector Engine
         │   ├── Event Capture
         │   ├── Fallback Chains
         │   ├── Healing Logic
         │   └── Stability Metrics
         │
         ├── Business Model
         │   ├── Flow Graph
         │   ├── State Detection
         │   └── Invariant Rules
         │
         ├── Multi-Language Codegen
         │   ├── Python (pytest/unittest)
         │   ├── Java (JUnit/TestNG)
         │   ├── Kotlin (KotlinTest)
         │   ├── JavaScript/TypeScript (WebdriverIO)
         │   ├── Go (testing)
         │   └── Ruby (RSpec)
         │
         ├── Backend Adapters
         │   ├── Appium v1/v2 + plugins
         │   ├── Espresso / UIAutomator (Android)
         │   ├── XCTest / XCUITest (iOS)
         │   ├── Detox (React Native)
         │   ├── Maestro (YAML-based)
         │   └── Playwright Mobile (future)
         │
         └── Static Analysis Module (when source available)
             ├── Flow Reconstruction
             ├── Security Checks
             ├── API Call Tracing
             ├── Fuzzing Point Detection
             └── Edge-Case Identification
```

---

## Development Phases (Evening/Weekend Work)

### **Phase 0: Foundation ✅ COMPLETED (1-2 weeks, 4-6 evenings)**

**Status**: ✅ Merged to master
**Branch**: `feature/phase0-foundation` (merged)

**Completed**:

- ✅ JSON-RPC 2.0 protocol specification (docs/PROTOCOL.md)
- ✅ Health check system (framework/health/)
- ✅ Daemon command for IDE plugin communication (stdio mode)
- ✅ CLI API documentation (docs/CLI_API.md)
- ✅ Protocol testing with manual clients

**Deliverables**:

- Clean, documented CLI API ✅
- Protocol specification (10 core methods) ✅
- Basic health check command ✅
- Updated architecture docs ✅

---

### **Phase 1: JetBrains Plugin MVP ✅ COMPLETED (1-2 months, 8-12 evenings)**

**Status**: ✅ Merged to master
**Branch**: `feature/phase1-ide-plugin-mvp` (merged)

**Completed**:

- ✅ Gradle build configuration (Kotlin + IntelliJ Platform SDK)
- ✅ plugin.xml with ToolWindow, Settings, Actions
- ✅ JSON-RPC Client (full async support)
- ✅ MTRDaemonService (application service)
- ✅ ToolWindow with 3 tabs (Devices, Inspector, Logs)
- ✅ DevicesPanel with device list table
- ✅ LogsPanel with auto-scroll
- ✅ Actions: Start/Stop Daemon, Refresh, Screenshot

**Deliverables**:

- JetBrains plugin installable locally ✅
- Device list (adb + simctl) ✅
- XML viewer placeholder ✅
- Logs streaming with notifications ✅
- Screenshot capture action ✅

**Tech Stack**:

- Kotlin 1.9.21 ✅
- IntelliJ SDK 2023.2+ ✅
- Gson for JSON ✅

---

### **Phase 2: Interactive UI Control ✅ COMPLETED (3-4 weeks, 6-8 evenings)**

**Status**: ✅ Merged to master
**Branch**: `feature/phase2-interactive-ui` (merged)

**Completed**:

- ✅ DeviceManager for listing Android/iOS devices
- ✅ Session management (start/stop)
- ✅ Screenshot capture (adb/simctl)
- ✅ Actions: tap, swipe, type via adb
- ✅ ScreenPanel - new tab in ToolWindow
- ✅ Interactive screenshot viewer with click-to-tap
- ✅ Coordinate mapping (screen → device)
- ✅ Auto-refresh after tap

**Deliverables**:

- Live device screen in ToolWindow ✅
- Clickable element overlay ✅
- Action execution (tap/swipe/type) ✅
- Visual feedback ✅

**Tech Stack**:

- BufferedImage + Graphics2D ✅
- adb exec-out screencap ✅
- xcrun simctl io screenshot ✅
- Base64 encoding/decoding ✅

---

### **Phase 3: Multi-Backend Abstraction 🚧 IN PROGRESS (1-2 months, 8-12 evenings)**

**Status**: 🚧 Starting now
**Branch**: `feature/phase3-multi-backend`

**Goals**:

- Stabilize current CLI core
- Define clear API/DSL contract
- Implement protocol layer (JSON-RPC)
- Documentation cleanup

**Deliverables**:

- Clean, documented CLI API
- Protocol specification
- Basic health check command
- Updated architecture docs

---

### **Phase 4: Environment Intelligence (2-3 weeks, 4-6 evenings)**

**Branch**: `feature/phase4-environment`

**Goals**:

- Auto-detect Appium version and plugins
- SDK detection (Android/Xcode)
- Compatibility warnings
- Quick actions (install/update commands)

**Deliverables**:

- Environment panel in ToolWindow
- Version checking
- Compatibility matrix
- "Copy install command" actions

**Tech Stack**:

- npm registry API
- appium plugin list
- android list sdk / xcode-select

---

### **Phase 5: Rust Core Integration (2-3 weeks, 6-8 evenings)**

**Branch**: `feature/phase5-rust-core` (already exists, needs polish)

**Goals**:

- Polish existing Rust modules
- Fix remaining bugs
- Performance benchmarks
- Python bindings optimization

**Deliverables**:

- Production-ready Rust core
- <50ms AST analysis
- <100ms event correlation
- Comprehensive tests

**Tech Stack**:

- Rust (pyo3, rayon, regex)
- Criterion for benchmarks

---

### **Phase 6: Smart Selectors & Healing (1-2 months, 8-12 evenings)**

**Branch**: `feature/phase6-smart-selectors`

**Goals**:

- Selector stability scoring
- Fallback chain generation
- Element matching (healing)
- Visual stability indicators in IDE

**Deliverables**:

- Selector scoring (0-100%)
- Hover hints in code editor
- Auto-healing suggestions
- Stability annotations

**Tech Stack**:

- ML (scikit-learn for scoring)
- Levenshtein distance (element matching)
- IntelliJ Intention/Inspection API

---

### **Phase 7: Multi-Language Codegen (1-2 months, 8-12 evenings)**

**Branch**: `feature/phase7-codegen`

**Goals**:

- Abstract action model
- Language-specific generators
- Support: Python, Java, Kotlin, JS/TS, Go, Ruby
- Page Object pattern support

**Deliverables**:

- Unified action DSL
- 6 language generators
- Customizable templates
- POM generation

**Tech Stack**:

- Jinja2 templates
- Abstract Syntax Trees
- Language wrappers (PyO3, NAPI-RS, CGO, FFI, JNI)

---

### **Phase 8: Flow & State Analysis (3-4 weeks, 6-8 evenings)**

**Branch**: `feature/phase8-flow-analysis`

**Goals**:

- Flow graph visualization in IDE
- State detection and tracking
- Invariant rule engine
- Coverage metrics

**Deliverables**:

- Interactive flow graph
- State transition diagram
- Invariant violation warnings
- Test coverage by flow

**Tech Stack**:

- GraphViz/PlantUML for visualization
- State machine pattern
- Rule engine (Python)

---

### **Phase 9: Static Analysis Module (1-2 months, 8-12 evenings)**

**Branch**: `feature/phase9-static-analysis`

**Goals** (when source code available):

- Flow reconstruction from source
- Security vulnerability detection
- API call tracing
- Fuzzing point identification
- Edge-case detection

**Deliverables**:

- Android (APK/source) analyzer
- iOS (IPA/source) analyzer
- Security report in IDE
- Annotated flow graph
- Auto-generated edge-case tests

**Tech Stack**:

- APKTool (Android)
- class-dump/Hopper (iOS)
- Semgrep (security rules)
- Custom AST parsers

---

### **Phase 10: LSP & Smart Autocomplete (3-4 weeks, 6-8 evenings)**

**Branch**: `feature/phase10-lsp`

**Goals**:

- Language Server Protocol implementation
- Flow-aware autocomplete
- Go-to-screen navigation
- Inline diagnostics

**Deliverables**:

- LSP server
- Autocomplete for screens/actions
- Jump to definition (screen)
- Real-time validation

**Tech Stack**:

- LSP protocol (JSON-RPC)
- IntelliJ LSP client
- Custom DSL parser

---

### **Phase 11: PRO Features & Monetization (1-2 months, 8-12 evenings)**

**Branch**: `feature/phase11-pro-features`

**Goals**:

- License key system (offline)
- PRO feature gating
- Enterprise policies
- Audit reports

**Deliverables**:

- License activation UI
- Feature flags by tier
- Team policy engine
- Usage reports

**Monetization Tiers**:

| Feature         | Free | PRO | Enterprise |
|-----------------|------|-----|------------|
| Device control  | ✅    | ✅   | ✅          |
| UI Inspector    | ✅    | ✅   | ✅          |
| Basic recording | ✅    | ✅   | ✅          |
| Smart selectors | ❌    | ✅   | ✅          |
| Healing         | ❌    | ✅   | ✅          |
| Multi-language  | ❌    | ✅   | ✅          |
| Flow analysis   | ❌    | ✅   | ✅          |
| Static analysis | ❌    | ❌   | ✅          |
| Security audit  | ❌    | ❌   | ✅          |
| Team policies   | ❌    | ❌   | ✅          |

**Pricing** (one-time purchase):

- **Individual**: $79 (PRO features)
- **Team** (5 seats): $299
- **Enterprise**: $1,499 (includes static analysis + support)

**Tech Stack**:

- RSA licensing
- Hardware fingerprinting
- JetBrains Marketplace integration

---

## Technology Stack

### **Core**

- **Rust**: High-performance modules (AST, correlation, file I/O)
- **Python**: ML layer, CLI orchestration
- **Kotlin**: JetBrains plugin

### **IDE Integration**

- IntelliJ Platform SDK
- Swing/JavaFX for UI
- LSP protocol

### **Mobile Automation**

- Appium (WebDriver)
- adb / xcrun
- scrcpy / simctl
- Espresso / XCTest

### **ML & Analytics**

- scikit-learn (Random Forest)
- NetworkX (flow graphs)
- SpaCy (NLP, if needed)

### **Build & Distribution**

- Gradle (plugin build)
- Cargo (Rust)
- Poetry (Python)
- GitHub Actions (CI/CD)
- JetBrains Marketplace

---

## Monetization Strategy (NO Servers, NO SaaS)

### **Business Model**: Sell Once, Use Forever

1. **Individual License**: $79
    - Smart selectors
    - Multi-language codegen
    - Flow analysis
    - Healing hints

2. **Team License**: $299 (5 seats)
    - All PRO features
    - Shared flow models
    - Team policies

3. **Enterprise License**: $1,499
    - All PRO features
    - Static analysis
    - Security audit
    - Priority email support (1 year)
    - Custom integrations

### **Distribution**:

- JetBrains Marketplace (primary)
- Direct sales (Gumroad / Stripe for Enterprise)
- No recurring subscriptions
- No servers to maintain
- Updates included (for 1 year)

### **Support Model**:

- Documentation + video tutorials (free)
- Community forum (free)
- Email support (Enterprise only, 1 year)
- No active consulting
- No workshops

---

## Development Principles

1. **Evening/Weekend Pace**: Each phase = 4-12 evenings, achievable in spare time
2. **Incremental Value**: Each phase delivers usable features
3. **No Servers**: Everything runs locally
4. **User Control**: Tool doesn't force upgrades or changes
5. **Backend Agnostic**: Support Appium first, expand gradually
6. **Multi-Language**: Wrappers for all popular languages
7. **Rust Core**: Performance-critical operations in Rust
8. **Python ML**: ML stays in Python ecosystem
9. **Extensible**: Plugin architecture for new backends/analyzers

---

## Success Metrics

### **Technical**:

- AST analysis: <50ms
- Event correlation: <100ms
- Selector healing: >85% success rate
- Plugin startup: <2s
- No memory leaks

### **Business** (Year 1):

- 1,000 free users
- 50 PRO licenses ($3,950)
- 5 team licenses ($1,495)
- 2 enterprise licenses ($2,998)
- **Total**: ~$8,500 first year

### **Year 2+**:

- 10,000 free users
- 200 PRO licenses
- 20 team licenses
- 10 enterprise licenses
- **Target**: $30K+ ARR

---

## Next Steps

1. **Commit this roadmap**
2. **Create Phase 0 branch** (`feature/phase0-foundation`)
3. **Start with protocol design** (JSON-RPC spec)
4. **Implement health check** (`mtr health`)
5. **Document CLI API** for plugin integration

---

## Notes for Solo Founder

- **You**: Strategy, UX, testing, product decisions
- **Cursor**: Implementation, refactoring, integration
- **Pace**: Sustainable, no burnout
- **Focus**: One phase at a time
- **Ship**: Release early, iterate based on feedback
- **Monetize**: As soon as Phase 6 (smart selectors) is done

**Remember**: This is a marathon, not a sprint. Quality > speed. Each phase should be production-ready before moving to
the next.
