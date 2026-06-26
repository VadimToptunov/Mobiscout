package com.mobiletest.recorder.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.util.xmlb.XmlSerializerUtil

/**
 * Persistent settings for Mobile Test Recorder plugin.
 *
 * Settings are stored in IDE configuration and persist across restarts.
 */
@Service
@State(
    name = "MobileTestRecorderSettings",
    storages = [Storage("MobileTestRecorder.xml")]
)
class MTRSettings : PersistentStateComponent<MTRSettings.State> {

    private var myState = State()

    /**
     * Settings state - all configurable options
     */
    data class State(
        // === Project Configuration ===
        var hasSourceCode: Boolean = false,
        var sourceCodePath: String = "",
        var buildPath: String = "",
        var targetPlatform: Platform = Platform.ANDROID,

        // === Analysis Options ===
        var analyzeApiLogs: Boolean = true,
        var enableSecurityScan: Boolean = false,
        var enablePerformanceAnalysis: Boolean = false,

        // === Test Framework ===
        var createNewFramework: Boolean = true,
        var existingFrameworkPath: String = "",
        var preferredLanguage: Language = Language.PYTHON,
        var testFramework: TestFramework = TestFramework.PYTEST,
        var automationBackend: AutomationBackend = AutomationBackend.APPIUM,

        // === Device Configuration ===
        var defaultEmulatorName: String = "",
        var defaultSimulatorName: String = "",
        var adbPath: String = "",
        var androidSdkPath: String = "",
        var xcodeSelectPath: String = "/usr/bin/xcode-select",

        // === Code Generation ===
        var pageObjectPattern: PageObjectPattern = PageObjectPattern.PAGE_OBJECT,
        var generateComments: Boolean = true,
        var generateDocstrings: Boolean = true,
        var useTypeHints: Boolean = true,

        // === Daemon Configuration ===
        var daemonPort: Int = 9876,
        var daemonAutoStart: Boolean = true,
        var daemonLogLevel: LogLevel = LogLevel.INFO,

        // === UI Preferences ===
        var screenshotRefreshInterval: Int = 1000,
        var showElementOverlay: Boolean = true,
        var highlightTappedElements: Boolean = true,

        // === License ===
        var licenseKey: String = "",
        var licenseEmail: String = ""
    )

    enum class Platform {
        ANDROID,
        IOS,
        BOTH
    }

    enum class Language {
        PYTHON,
        JAVA,
        KOTLIN,
        SWIFT,
        JAVASCRIPT,
        TYPESCRIPT,
        GO
    }

    enum class TestFramework {
        PYTEST,
        UNITTEST,
        JUNIT,
        TESTNG,
        XCTEST,
        MOCHA,
        JEST,
        GO_TEST
    }

    enum class AutomationBackend {
        APPIUM,
        ESPRESSO,
        XCTEST,
        DETOX,
        MAESTRO
    }

    enum class PageObjectPattern {
        PAGE_OBJECT,
        SCREENPLAY,
        PAGE_FACTORY,
        SIMPLE
    }

    enum class LogLevel {
        DEBUG,
        INFO,
        WARNING,
        ERROR
    }

    override fun getState(): State = myState

    override fun loadState(state: State) {
        XmlSerializerUtil.copyBean(state, myState)
    }

    companion object {
        @JvmStatic
        fun getInstance(): MTRSettings {
            return ApplicationManager.getApplication().getService(MTRSettings::class.java)
        }
    }

    // Convenience accessors
    var hasSourceCode: Boolean
        get() = myState.hasSourceCode
        set(value) { myState.hasSourceCode = value }

    var sourceCodePath: String
        get() = myState.sourceCodePath
        set(value) { myState.sourceCodePath = value }

    var buildPath: String
        get() = myState.buildPath
        set(value) { myState.buildPath = value }

    var targetPlatform: Platform
        get() = myState.targetPlatform
        set(value) { myState.targetPlatform = value }

    var analyzeApiLogs: Boolean
        get() = myState.analyzeApiLogs
        set(value) { myState.analyzeApiLogs = value }

    var enableSecurityScan: Boolean
        get() = myState.enableSecurityScan
        set(value) { myState.enableSecurityScan = value }

    var enablePerformanceAnalysis: Boolean
        get() = myState.enablePerformanceAnalysis
        set(value) { myState.enablePerformanceAnalysis = value }

    var preferredLanguage: Language
        get() = myState.preferredLanguage
        set(value) { myState.preferredLanguage = value }

    var testFramework: TestFramework
        get() = myState.testFramework
        set(value) { myState.testFramework = value }

    var automationBackend: AutomationBackend
        get() = myState.automationBackend
        set(value) { myState.automationBackend = value }

    var daemonAutoStart: Boolean
        get() = myState.daemonAutoStart
        set(value) { myState.daemonAutoStart = value }

    var screenshotRefreshInterval: Int
        get() = myState.screenshotRefreshInterval
        set(value) { myState.screenshotRefreshInterval = value }
}
