plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "ru.liftcontrol.liftcontrol_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // Stable beta identifier, separate from the future production application.
        applicationId = "ru.liftcontrol.app.beta"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    val betaBuild = System.getenv("LIFTCONTROL_BETA") == "true"
    if (gradle.startParameter.taskNames.any { it.contains("Release", ignoreCase = true) } && !betaBuild) {
        throw GradleException("This is a beta-only signing configuration. Set LIFTCONTROL_BETA=true for a test APK; production needs a separate release key.")
    }
    buildTypes {
        release {
            // Beta only. CI caches this test key; a production signing key is never committed.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

// FileProvider grants access to one explicitly opened PDF, never the private directory.
dependencies { implementation("androidx.core:core-ktx:1.17.0") }
