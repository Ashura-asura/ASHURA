package com.ashura.tutor.data

import android.content.res.AssetManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.security.MessageDigest

/** A bundled, open-licensed study note that the learner can add to the local library. */
data class StudySet(
    val id: String,
    val subjectId: String,
    val subjectName: String,
    val title: String,
    val file: String,
    val source: String,
    val license: String,
    val licenseUrl: String,
    val chars: Int,
    val sha256: String
)

data class StudySubject(
    val id: String,
    val name: String,
    val level: String,
    val sets: List<StudySet>
)

data class StudyLibrary(
    val version: Int,
    val generatedAt: String,
    val license: String,
    val licenseUrl: String,
    val notice: String,
    val subjects: List<StudySubject>
) {
    val allSets: List<StudySet> get() = subjects.flatMap { it.sets }
    val count: Int get() = subjects.sumOf { it.sets.size }
}

/**
 * Reads the study packs bundled under `assets/study_sets` (spec: offline-first content).
 *
 * The manifest records the source URL, licence and SHA-256 of every note. [readSet] verifies the
 * checksum before the text reaches the library, so a partially written or tampered asset is rejected
 * instead of being presented as trusted study material. The notes are condensed Wikipedia excerpts
 * licensed CC BY-SA 4.0; the app shows that attribution in the picker.
 */
class StudyPackRepository(private val assets: AssetManager) {
    private val root = "study_sets"

    fun loadCatalog(): StudyLibrary {
        val raw = assets.open("$root/manifest.json").bufferedReader(Charsets.UTF_8).use { it.readText() }
        val json = JSONObject(raw)
        require(json.optString("format") == "ashura-study-packs") { "Unknown study-pack format." }
        val subjectsJson = json.getJSONArray("subjects")
        val subjects = ArrayList<StudySubject>(subjectsJson.length())
        for (i in 0 until subjectsJson.length()) {
            val subjectJson = subjectsJson.getJSONObject(i)
            val subjectId = subjectJson.getString("id")
            val subjectName = subjectJson.getString("name")
            val level = subjectJson.optString("level")
            val setsJson = subjectJson.getJSONArray("sets")
            val sets = ArrayList<StudySet>(setsJson.length())
            for (j in 0 until setsJson.length()) {
                val setJson = setsJson.getJSONObject(j)
                sets.add(
                    StudySet(
                        id = setJson.getString("id"),
                        subjectId = subjectId,
                        subjectName = subjectName,
                        title = setJson.getString("title"),
                        file = setJson.getString("file"),
                        source = setJson.getString("source"),
                        license = setJson.getString("license"),
                        licenseUrl = setJson.getString("licenseUrl"),
                        chars = setJson.optInt("chars"),
                        sha256 = setJson.getString("sha256")
                    )
                )
            }
            subjects.add(StudySubject(subjectId, subjectName, level, sets))
        }
        return StudyLibrary(
            version = json.optInt("version", 1),
            generatedAt = json.optString("generatedAt"),
            license = json.optString("license"),
            licenseUrl = json.optString("licenseUrl"),
            notice = json.optString("notice"),
            subjects = subjects
        )
    }

    /** Reads one note and verifies the checksum recorded when the pack was built. */
    suspend fun readSet(set: StudySet): String = withContext(Dispatchers.IO) {
        val bytes = assets.open("$root/${set.file}").use { it.readBytes() }
        val actual = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        require(actual.equals(set.sha256, ignoreCase = true)) {
            "This study set failed its integrity check. Reinstall the app to repair it."
        }
        String(bytes, Charsets.UTF_8)
    }
}
