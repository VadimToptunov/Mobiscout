plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.21"
    id("org.jetbrains.intellij") version "1.17.0"
}

group = "com.mobiletest"
version = "0.1.0-SNAPSHOT"

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib")
    implementation("com.google.code.gson:gson:2.14.0")
    
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.1")
    testImplementation("org.mockito:mockito-core:5.23.0")
}

// Configure Gradle IntelliJ Plugin
// Read more: https://plugins.jetbrains.com/docs/intellij/tools-gradle-intellij-plugin.html
intellij {
    version.set("2023.2.5")
    type.set("IC") // Target IDE Platform: IC = IntelliJ IDEA Community

    plugins.set(listOf(
        // Add any additional plugin dependencies here
    ))
}

tasks {
    // Set the JVM compatibility versions
    withType<JavaCompile> {
        sourceCompatibility = "17"
        targetCompatibility = "17"
    }
    
    withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        kotlinOptions.jvmTarget = "17"
    }

    patchPluginXml {
        sinceBuild.set("232")
        untilBuild.set("241.*")
        
        pluginDescription.set("""
            <h1>Mobile Test Recorder</h1>
            <p>Intelligent mobile testing platform with interactive UI control and smart test generation.</p>
            <h2>Features:</h2>
            <ul>
                <li>📱 Device management (Android/iOS)</li>
                <li>🔍 UI Tree inspector</li>
                <li>📊 Device logs</li>
                <li>🎯 Interactive UI control</li>
                <li>🧠 Smart selector generation</li>
                <li>🔄 Flow-based test generation</li>
                <li>🌍 Multi-language support</li>
            </ul>
        """.trimIndent())
        
        changeNotes.set("""
            <h2>v0.1.0-SNAPSHOT</h2>
            <ul>
                <li>Phase 1: IDE Plugin MVP</li>
                <li>Basic ToolWindow with device list</li>
                <li>UI Tree viewer</li>
                <li>Device logs</li>
                <li>JSON-RPC client</li>
            </ul>
        """.trimIndent())
    }

    signPlugin {
        certificateChain.set(System.getenv("CERTIFICATE_CHAIN"))
        privateKey.set(System.getenv("PRIVATE_KEY"))
        password.set(System.getenv("PRIVATE_KEY_PASSWORD"))
    }

    publishPlugin {
        token.set(System.getenv("PUBLISH_TOKEN"))
    }
    
    test {
        useJUnitPlatform()
    }
}
