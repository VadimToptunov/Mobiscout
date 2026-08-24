package com.mobiletest.recorder.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.util.xmlb.XmlSerializerUtil

/**
 * Persistent settings for the Mobiscout plugin.
 *
 * Only settings the plugin actually reads live here. The old state carried ~20 knobs left
 * over from the removed setup wizard that nothing consumed — a user turned them and nothing
 * happened. Removing a persisted field is backward-safe: an old MobileTestRecorder.xml with
 * extra keys just ignores them on load.
 */
@Service
@State(
    name = "MobileTestRecorderSettings",
    storages = [Storage("MobileTestRecorder.xml")]
)
class MTRSettings : PersistentStateComponent<MTRSettings.State> {

    private var myState = State()

    data class State(
        // Defaults for the Generate dialog.
        var targetPlatform: Platform = Platform.ANDROID,
        var preferredLanguage: Language = Language.PYTHON,
        var createNewFramework: Boolean = true,
        var existingFrameworkPath: String = "",
        // Preferred device to auto-boot when nothing is running (else the first candidate).
        var defaultEmulatorName: String = "",
        var defaultSimulatorName: String = "",
        // Start the engine when the IDE opens.
        var daemonAutoStart: Boolean = true,
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
    var targetPlatform: Platform
        get() = myState.targetPlatform
        set(value) { myState.targetPlatform = value }

    var preferredLanguage: Language
        get() = myState.preferredLanguage
        set(value) { myState.preferredLanguage = value }

    var createNewFramework: Boolean
        get() = myState.createNewFramework
        set(value) { myState.createNewFramework = value }

    var existingFrameworkPath: String
        get() = myState.existingFrameworkPath
        set(value) { myState.existingFrameworkPath = value }

    var defaultEmulatorName: String
        get() = myState.defaultEmulatorName
        set(value) { myState.defaultEmulatorName = value }

    var defaultSimulatorName: String
        get() = myState.defaultSimulatorName
        set(value) { myState.defaultSimulatorName = value }

    var daemonAutoStart: Boolean
        get() = myState.daemonAutoStart
        set(value) { myState.daemonAutoStart = value }
}
