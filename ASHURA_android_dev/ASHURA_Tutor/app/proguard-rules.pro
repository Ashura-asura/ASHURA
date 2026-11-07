# Room keeps the generated database implementation; Room's consumer rules cover most of it,
# these are defensive against future R8 iterations.
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class com.ashura.tutor.data.AppDatabase_Impl { *; }
-keep @androidx.room.Entity class *
-dontwarn org.jetbrains.annotations.**

# LiteRT-LM reaches its native engine through JNI and reflection-based JSON conversion.
-keep class com.google.ai.edge.litertlm.** { *; }
-keepclassmembers class com.google.ai.edge.litertlm.** { *; }
-dontwarn com.google.ai.edge.litertlm.**
# Gson is used by the runtime to serialise conversation/tool JSON.
-keep class com.google.gson.** { *; }
-dontwarn com.google.gson.**

# Keep source-file/line metadata for readable release crash reports.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
