package com.ashura.tutor.domain.runtime

import java.io.InputStream
import java.security.MessageDigest

/** Integrity and storage checks that must pass before a downloaded model is ever loaded (spec §6.3, §18.2). */
object ModelFileVerifier {
    /** Streaming SHA-256 (lowercase hex); never loads the whole model into memory. */
    fun sha256Hex(input: InputStream, onProgress: (bytesRead: Long) -> Unit = {}): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buf = ByteArray(1 shl 16)
        var total = 0L
        while (true) {
            val n = input.read(buf)
            if (n < 0) break
            digest.update(buf, 0, n)
            total += n
            onProgress(total)
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    sealed interface Verdict {
        data object Valid : Verdict
        data class Invalid(val reason: String) : Verdict
    }

    fun verify(input: InputStream, manifest: ModelManifest): Verdict {
        val problems = manifest.problems()
        if (problems.isNotEmpty()) return Verdict.Invalid("Manifest invalid: ${problems.joinToString("; ")}")
        val actual = sha256Hex(input)
        // Hash comparison of public data; constant-time comparison is not needed.
        return if (actual == manifest.artifactSha256) Verdict.Valid
        else Verdict.Invalid("Checksum mismatch: the file is corrupt or not the expected model.")
    }

    /** Requires the model plus a safety reserve; models are downloaded to a temp file first, then renamed. */
    fun hasSpaceFor(modelBytes: Long, freeBytes: Long, reserveBytes: Long = 1L shl 30): Boolean =
        modelBytes > 0 && freeBytes >= modelBytes + reserveBytes
}
