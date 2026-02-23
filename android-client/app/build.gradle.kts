import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.resona.client"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.resona.client.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "1.0.1"
    }

    signingConfigs {
        create("release") {
            val keystoreProperties = Properties()
            val keystorePropertiesFile = rootProject.file("local.properties")
            if (keystorePropertiesFile.exists()) {
                keystoreProperties.load(FileInputStream(keystorePropertiesFile))
            }

            val keystoreFile = keystoreProperties.getProperty("RELEASE_STORE_FILE_NEW")
                ?: project.findProperty("RELEASE_STORE_FILE_NEW") as String?
                ?: keystoreProperties.getProperty("RELEASE_STORE_FILE")
                ?: project.findProperty("RELEASE_STORE_FILE") as String?
            
            if (keystoreFile != null) {
                storeFile = file(keystoreFile)
                storePassword = keystoreProperties.getProperty("RELEASE_STORE_PASSWORD_NEW") 
                    ?: project.findProperty("RELEASE_STORE_PASSWORD_NEW") as String?
                    ?: keystoreProperties.getProperty("RELEASE_STORE_PASSWORD") 
                    ?: project.findProperty("RELEASE_STORE_PASSWORD") as String?
                keyAlias = keystoreProperties.getProperty("RELEASE_KEY_ALIAS_NEW") 
                    ?: project.findProperty("RELEASE_KEY_ALIAS_NEW") as String?
                    ?: keystoreProperties.getProperty("RELEASE_KEY_ALIAS") 
                    ?: project.findProperty("RELEASE_KEY_ALIAS") as String?
                keyPassword = keystoreProperties.getProperty("RELEASE_KEY_PASSWORD_NEW") 
                    ?: project.findProperty("RELEASE_KEY_PASSWORD_NEW") as String?
                    ?: keystoreProperties.getProperty("RELEASE_KEY_PASSWORD") 
                    ?: project.findProperty("RELEASE_KEY_PASSWORD") as String?
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.lifecycle:lifecycle-process:2.7.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
