import org.jetbrains.intellij.platform.gradle.TestFrameworkType

// Migrated to the IntelliJ Platform Gradle Plugin 2.x (the 1.x line is frozen and
// can't target 2024.2+ IDEs). Requires JDK 21 and Gradle 8.5+.
plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "2.1.0"
    id("org.jetbrains.intellij.platform") version "2.2.1"
}

group = "com.mobiletest"
version = "0.1.0-SNAPSHOT"

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    implementation("com.google.code.gson:gson:2.14.0")

    testImplementation("org.junit.jupiter:junit-jupiter:6.1.2")
    testImplementation("org.mockito:mockito-core:5.23.0")

    intellijPlatform {
        // Build against IntelliJ IDEA Community 2024.2 (the 2.x baseline).
        create("IC", "2024.2")
        testFramework(TestFrameworkType.Platform)
    }
}

intellijPlatform {
    pluginConfiguration {
        // Name/description/change-notes come from META-INF/plugin.xml — kept honest
        // there, so we don't override them here.
        ideaVersion {
            sinceBuild = "242"          // 2024.2+
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
        ides {
            // Pin released IDEs — `recommended()` pulls unreleased EAP versions
            // (e.g. ideaIC:2025.3) that aren't in the repository yet, failing CI.
            ide("IC", "2024.2")
            ide("IC", "2024.3")
        }
    }
}

kotlin {
    jvmToolchain(21)
}

tasks {
    test {
        useJUnitPlatform()
    }
}
