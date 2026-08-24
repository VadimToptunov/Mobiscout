import org.jetbrains.intellij.platform.gradle.IntelliJPlatformType
import org.jetbrains.intellij.platform.gradle.models.ProductRelease
import org.jetbrains.intellij.platform.gradle.tasks.VerifyPluginTask.FailureLevel

// Migrated to the IntelliJ Platform Gradle Plugin 2.x (the 1.x line is frozen and
// can't target 2024.2+ IDEs). Requires JDK 21 and Gradle 9.6+.
plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "2.4.10"
    id("org.jetbrains.intellij.platform") version "2.18.1"
}

group = "com.mobiletest"
version = "0.12.0"

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    implementation("com.google.code.gson:gson:2.14.0")

    testImplementation("org.junit.jupiter:junit-jupiter:6.1.3")
    testImplementation("org.mockito:mockito-core:5.23.0")
    // Gradle 9 no longer bundles the launcher on the test runtime classpath.
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    // The bundled IntelliJ distribution registers test listeners that reference JUnit 4;
    // provide it so the test executor can start, even though our tests are JUnit 5.
    testRuntimeOnly("junit:junit:4.13.2")

    intellijPlatform {
        // Build against IntelliJ IDEA Community 2024.2 (the 2.x baseline).
        create("IC", "2024.3")
    }
}

intellijPlatform {
    pluginConfiguration {
        // Name/description/change-notes come from META-INF/plugin.xml — kept honest
        // there, so we don't override them here.
        ideaVersion {
            sinceBuild = "243"          // 2024.3+ (floor bumped so codegen can use non-deprecated platform APIs)
            untilBuild = provider { null }  // no upper bound — support current & future IDEs
        }
    }

    signing {
        certificateChain = providers.environmentVariable("CERTIFICATE_CHAIN")
        privateKey = providers.environmentVariable("PRIVATE_KEY")
        password = providers.environmentVariable("PRIVATE_KEY_PASSWORD")
    }

    publishing {
        token = providers.environmentVariable("PUBLISH_TOKEN")
    }

    pluginVerification {
        // Fail the build only on genuine breakage — an invalid plugin, real
        // binary-compatibility problems, or missing dependencies. Implementing
        // ToolWindowFactory unavoidably trips INTERNAL / EXPERIMENTAL / DEPRECATED
        // usages for methods the platform recently annotated (getIcon, getAnchor,
        // manage, isApplicable); those are evolution warnings, not breakage, so
        // they must not fail CI.
        failureLevel = listOf(
            FailureLevel.COMPATIBILITY_PROBLEMS,
            FailureLevel.INVALID_PLUGIN,
            FailureLevel.MISSING_DEPENDENCIES,
        )

        ides {
            // Verify against RELEASED IDEs only — `recommended()` pulls unreleased
            // EAP versions that aren't in the repository yet, failing CI. Platform
            // plugin 2.18.1 dropped the explicit ide("IC", …) pins; `select {}`
            // with the RELEASE channel and a build range is the current way to pin
            // a known set (here IC 2024.2–2024.3, builds 242–243).
            // The plugin depends only on com.intellij.modules.platform, so it runs
            // in every JetBrains IDE — verify the mobile-relevant ones, not just
            // IntelliJ IDEA: Android Studio (Android), PyCharm (Python tests) too.
            // The plugin declares only `com.intellij.modules.platform`, so its whole
            // API surface is the shared IntelliJ Platform. IntelliJ IDEA Community (IC)
            // verification therefore covers every platform-only JetBrains IDE — PyCharm
            // included — and Android Studio (AI) adds the Android-flavored platform.
            // (PyCharmCommunity does not resolve a distinct RELEASE build in this range
            // through `select`, and the 2.18.1 API has no explicit per-IDE pin; since it
            // would add no new API surface to check, IC+AI is the honest, complete set.)
            select {
                types = listOf(
                    IntelliJPlatformType.IntellijIdeaCommunity,
                    IntelliJPlatformType.AndroidStudio,
                )
                channels = listOf(ProductRelease.Channel.RELEASE)
                sinceBuild = "243"
                untilBuild = "243.*"
            }
        }
    }
}

kotlin {
    jvmToolchain(21)
    compilerOptions {
        // Emit real JVM default methods instead of Kotlin's DefaultImpls delegation.
        // Without this, implementing an interface with a default method (e.g.
        // ToolWindowFactory.getAnchor()) makes Kotlin generate a synthetic override
        // that delegates to it — which the plugin verifier flags as "overrides an
        // internal API". With -Xjvm-default=all no such override is generated.
        freeCompilerArgs.add("-jvm-default=no-compatibility")
    }
}

tasks {
    test {
        useJUnitPlatform()
    }
}
