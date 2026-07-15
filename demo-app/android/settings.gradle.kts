pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // Regula Document Reader SDK
        maven {
            url = uri("https://maven.regulaforensics.com/RegulaDocumentReader")
        }
    }
}

rootProject.name = "FinDemo"
include(":app")
include(":mobiscout-sdk")

