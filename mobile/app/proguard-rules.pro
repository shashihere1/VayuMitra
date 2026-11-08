# Keep kotlinx.serialization generated serializers.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.vayumitra.model.** { *; }
-keep,includedescriptorclasses class com.vayumitra.**$$serializer { *; }
-keepclassmembers class com.vayumitra.** {
    *** Companion;
}

# TensorFlow Lite
-keep class org.tensorflow.lite.** { *; }
-dontwarn org.tensorflow.lite.**

# HiveMQ / Netty (reflective bits)
-dontwarn io.netty.**
-dontwarn com.hivemq.**
