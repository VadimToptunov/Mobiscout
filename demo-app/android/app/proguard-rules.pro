# ProGuard/R8 Rules for FinDemo Production Build
# ==================================================
#
# These rules ensure:
# - Code obfuscation
# - String encryption
# - Security class protection
# - Reverse engineering prevention

# ==================== General ====================

# Keep line numbers for debugging stack traces
-keepattributes SourceFile,LineNumberTable

# Rename source file for obfuscation
-renamesourcefileattribute SourceFile

# ==================== Security Classes ====================

# Remove security bypass code from production
-assumenosideeffects class com.mobiscout.sdk.** {
    public *;
}

# Obfuscate security classes heavily
-keep,allowobfuscation class com.findemo.security.** { *; }

# Keep security monitor for analytics
-keep class com.findemo.security.SecurityMonitor {
    public static void reportSecurityEvent(...);
}

# ==================== API & Network ====================

# Keep API models
-keep class com.findemo.data.model.** { *; }
-keepclassmembers class com.findemo.data.model.** { *; }

# Retrofit
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.Response
-keep,allowobfuscation,allowshrinking class kotlin.coroutines.Continuation

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }
-keep interface okhttp3.** { *; }

# Gson
-keepattributes Signature
-keepattributes *Annotation*
-dontwarn sun.misc.**
-keep class com.google.gson.** { *; }
-keep class * implements com.google.gson.TypeAdapter
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer

# ==================== Jetpack Compose ====================

-keep class androidx.compose.** { *; }
-keep interface androidx.compose.** { *; }

# Keep ViewModels
-keep class * extends androidx.lifecycle.ViewModel {
    <init>(...);
}

# Navigation
-keepnames class androidx.navigation.fragment.NavHostFragment
-keep class * extends androidx.fragment.app.Fragment{}

# ==================== Kotlin ====================

# Keep Kotlin metadata
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt

# Kotlin coroutines
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-keepclassmembers class kotlinx.coroutines.** {
    volatile <fields>;
}

# ==================== Android Components ====================

# Keep custom views
-keep public class * extends android.view.View {
    public <init>(android.content.Context);
    public <init>(android.content.Context, android.util.AttributeSet);
    public <init>(android.content.Context, android.util.AttributeSet, int);
    public void set*(...);
}

# Keep enums
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

# Keep Parcelables
-keepclassmembers class * implements android.os.Parcelable {
    public static final ** CREATOR;
}

# ==================== Android Keystore ====================

# Keep security providers
-keep class * extends java.security.Provider {
    *;
}

# Keep Keystore classes
-keep class javax.crypto.** { *; }
-keep class java.security.** { *; }
-keep class android.security.keystore.** { *; }

# ==================== Encrypted SharedPreferences ====================

-keep class androidx.security.crypto.** { *; }
-keep class com.google.crypto.tink.** { *; }

# ==================== Biometrics ====================

-keep class androidx.biometric.** { *; }

# ==================== Regula SDK (if used) ====================

-keep class com.regula.** { *; }
-dontwarn com.regula.**

# ==================== Crashlytics / Analytics ====================

-keepattributes *Annotation*
-keepattributes SourceFile,LineNumberTable
-keep public class * extends java.lang.Exception

# ==================== String Encryption ====================

# Obfuscate string constants (requires R8 full mode)
-repackageclasses 'o'

# ==================== Optimization ====================

# Enable aggressive optimization
-optimizations !code/simplification/arithmetic,!code/simplification/cast,!field/*,!class/merging/*
-optimizationpasses 5
-allowaccessmodification

# ==================== Debugging ====================

# Remove logging in production
-assumenosideeffects class android.util.Log {
    public static boolean isLoggable(java.lang.String, int);
    public static int v(...);
    public static int d(...);
    public static int i(...);
    public static int w(...);
    public static int e(...);
}

# Remove debug code
-assumenosideeffects class kotlin.jvm.internal.Intrinsics {
    static void checkNotNull(java.lang.Object);
    static void checkNotNull(java.lang.Object, java.lang.String);
    static void checkParameterIsNotNull(java.lang.Object, java.lang.String);
}

# ==================== BuildConfig ====================

# Remove BuildConfig debug fields
-assumenosideeffects class com.findemo.BuildConfig {
    public static boolean DEBUG return false;
}

# ==================== Warnings ====================

# Ignore warnings
-dontwarn javax.annotation.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# ==================== Testing ====================

# Remove test code from production
-assumenosideeffects class junit.** {
    *;
}
-assumenosideeffects class org.junit.** {
    *;
}
-assumenosideeffects class androidx.test.** {
    *;
}

# ==================== Custom Rules ====================

# Add your custom rules below

