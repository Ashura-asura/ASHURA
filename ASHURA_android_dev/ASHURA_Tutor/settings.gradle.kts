pluginManagement {
  repositories {
    google {
      content {
        includeGroupByRegex("com\\.android.*")
        includeGroupByRegex("com\\.google.*")
        includeGroupByRegex("androidx.*")
      }
    }
    mavenCentral()
    gradlePluginPortal()
  }
  plugins {
    // AGP 8.13 is required by KSP2 2.3.x, which in turn supports Kotlin 2.4 metadata.
    id("com.android.application") version "8.13.2"
    // LiteRT-LM 0.19.1 is compiled with Kotlin 2.4 metadata, so the compiler must be >= 2.4.0.
    id("org.jetbrains.kotlin.android") version "2.4.0"
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.0"
    id("com.google.devtools.ksp") version "2.3.13"
  }
}

dependencyResolutionManagement {
  repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
  repositories {
    google()
    mavenCentral()
  }
}

rootProject.name = "ashura-tutor"

include(":app")
