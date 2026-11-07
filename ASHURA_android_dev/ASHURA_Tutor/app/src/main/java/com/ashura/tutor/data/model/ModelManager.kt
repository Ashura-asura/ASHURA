package com.ashura.tutor.data.model

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.provider.OpenableColumns
import com.ashura.tutor.domain.runtime.DeviceState
import com.ashura.tutor.domain.runtime.LiteRtLmModelRuntime
import com.ashura.tutor.domain.runtime.LoadResult
import com.ashura.tutor.domain.runtime.ModelCatalog
import com.ashura.tutor.domain.runtime.ModelFileVerifier
import com.ashura.tutor.domain.runtime.ModelManifest
import com.ashura.tutor.domain.runtime.RamTier
import com.ashura.tutor.domain.runtime.ResourcePolicy
import com.ashura.tutor.domain.runtime.RuntimeMetrics
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** User-visible state of the single on-device model slot (spec §6.1: never two models loaded). */
sealed interface ModelState {
    data object NotInstalled : ModelState
    data object Importing : ModelState
    data class Downloading(val manifest: ModelManifest, val bytes: Long, val total: Long) : ModelState
    data class Verifying(val manifest: ModelManifest) : ModelState
    data class Loading(val manifest: ModelManifest) : ModelState
    data class Ready(val manifest: ModelManifest, val loaded: Boolean) : ModelState
    data class Failed(val manifest: ModelManifest?, val message: String) : ModelState
}

/**
 * Owns the model slot: download, SAF import, checksum verification, atomic install, load/unload and
 * deletion. Network access happens only inside [download], which the UI invokes from an explicit
 * consent button; the rest of the app stays offline.
 *
 * Every install path enforces:
 *  - the artifact is a catalog entry with a pinned revision, size and SHA-256;
 *  - the device RAM tier can hold it (spec §16.1);
 *  - there is enough free storage plus a 1 GB reserve;
 *  - the file is written to `.part`, hashed while streaming, then renamed.
 */
class ModelManager(
    private val context: Context,
    private val runtime: LiteRtLmModelRuntime,
    private val scope: CoroutineScope,
    val catalog: List<ModelManifest> = ModelCatalog.entries,
    private val installDir: File = File(context.filesDir, "models"),
    val deviceTier: RamTier = deviceRamTier(context)
) {
    private val _state = MutableStateFlow<ModelState>(ModelState.NotInstalled)
    val state: StateFlow<ModelState> = _state.asStateFlow()

    /** Last measured runtime timings, passed through from the engine for the diagnostics panel. */
    val metrics: StateFlow<RuntimeMetrics?> = runtime.metrics

    /** Free space on the install volume, shown next to the model size. */
    fun freeStorageBytes(): Long = installDir.usableSpace

    private var activeJob: Job? = null
    @Volatile private var connection: HttpURLConnection? = null
    @Volatile private var cancelRequested = false

    init {
        installDir.mkdirs()
        installDir.listFiles()?.filter { it.name.endsWith(".part") }?.forEach { it.delete() }
        refresh()
    }

    /** Reconciles the filesystem with the catalog without hashing the whole file. */
    fun refresh() {
        installDir.mkdirs()
        val installed = catalog.mapNotNull { manifest ->
            LiteRtLmModelRuntime.fileFor(installDir, manifest).takeIf { it.isFile }?.let { manifest to it }
        }
        when {
            installed.isEmpty() -> _state.value = ModelState.NotInstalled
            installed.size > 1 -> _state.value = ModelState.Failed(
                null,
                "More than one model file is installed. Keep one and delete the others."
            )
            else -> {
                val (manifest, file) = installed.single()
                if (file.length() != manifest.sizeBytes) {
                    _state.value = ModelState.Failed(
                        manifest,
                        "The installed model file is incomplete (${file.length()} of ${manifest.sizeBytes} bytes). " +
                            "Delete it and download again."
                    )
                } else {
                    val loaded = runtime.health().loaded
                    _state.value = ModelState.Ready(manifest, loaded)
                }
            }
        }
    }

    fun recommended(): ModelManifest? = ModelCatalog.recommendedFor(deviceTier)

    /** Returns null when [manifest] may be installed; otherwise a user-facing reason. */
    fun installProblem(manifest: ModelManifest): String? = when {
        catalog.none { it.id == manifest.id } -> "This model is not in the verified catalog."
        manifest.problems().isNotEmpty() -> "The model manifest is invalid."
        !manifest.supports(deviceTier) ->
            "This model needs a ${manifest.minimumTier.label} device; this device is ${deviceTier.label}."
        manifest.downloadUrl?.startsWith("https://") != true -> "The download URL must use HTTPS."
        manifest.sizeBytes <= 0L -> "The model size is not pinned."
        else -> null
    }

    /** Starts an explicit, user-consented HTTPS download. Returns false when it was refused. */
    fun download(manifest: ModelManifest): Boolean {
        if (activeJob?.isActive == true) return false
        val problem = installProblem(manifest) ?: run {
            if (!isOnline()) "No network connection. Connect once to download the model."
            else if (!ModelFileVerifier.hasSpaceFor(manifest.sizeBytes, installDir.usableSpace)) {
                "Not enough free storage. The model needs ${manifest.sizeBytes} bytes plus a 1 GB reserve."
            } else null
        }
        if (problem != null) {
            _state.value = ModelState.Failed(manifest, problem)
            return false
        }
        val url = manifest.downloadUrl ?: return false
        cancelRequested = false
        activeJob = scope.launch { runDownload(manifest, url) }
        return true
    }

    /** Imports a user-picked `.litertlm` file through SAF. The file must match a pinned catalog hash. */
    fun importFromUri(uri: Uri) {
        if (activeJob?.isActive == true) return
        cancelRequested = false
        activeJob = scope.launch { runImport(uri) }
    }

    fun loadInstalled() {
        if (activeJob?.isActive == true) return
        val ready = (state.value as? ModelState.Ready) ?: return
        if (ready.loaded) return
        _state.value = ModelState.Loading(ready.manifest)
        activeJob = scope.launch {
            runtime.unload()
            val policy = ResourcePolicy.choose(DeviceState(deviceTier))
            when (val result = runtime.load(ready.manifest, ResourcePolicy.budgetFor(policy))) {
                LoadResult.Loaded -> _state.value = ModelState.Ready(ready.manifest, loaded = true)
                is LoadResult.Failed -> _state.value = ModelState.Failed(ready.manifest, result.reason)
            }
        }
    }

    /** Loads an already verified model at startup without requiring the learner to open Settings. */
    fun autoLoadInstalled() {
        val ready = (state.value as? ModelState.Ready) ?: return
        if (!ready.loaded) loadInstalled()
    }

    fun unload() {
        runtime.unload()
        val current = state.value
        if (current is ModelState.Ready) _state.value = current.copy(loaded = false)
    }

    fun cancelDownload() {
        cancelRequested = true
        activeJob?.cancel()
        runCatching { connection?.disconnect() }
    }

    fun deleteInstalled() {
        cancelDownload()
        scope.launch {
            runtime.unload()
            withContext(Dispatchers.IO) {
                installDir.listFiles()?.forEach { it.delete() }
            }
            _state.value = ModelState.NotInstalled
        }
    }

    private suspend fun runDownload(manifest: ModelManifest, url: String) = withContext(Dispatchers.IO) {
        val target = LiteRtLmModelRuntime.fileFor(installDir, manifest)
        val temp = File(installDir, "${manifest.id}.part")
        var conn: HttpURLConnection? = null
        try {
            runtime.unload()
            deleteOtherModelFiles(manifest)
            temp.delete()
            _state.value = ModelState.Downloading(manifest, 0, manifest.sizeBytes)

            conn = (URL(url).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = true
                connectTimeout = 30_000
                readTimeout = 60_000
                requestMethod = "GET"
                setRequestProperty("User-Agent", "ASHURA-Tutor/0.3 (offline tutor)")
            }
            connection = conn
            val code = conn.responseCode
            if (code !in 200..299) error("The model server returned HTTP $code.")
            val declared = conn.contentLengthLong
            if (declared > 0 && declared != manifest.sizeBytes) {
                error("The server advertised $declared bytes but the manifest pins ${manifest.sizeBytes}.")
            }

            val digest = MessageDigest.getInstance("SHA-256")
            var downloaded = 0L
            var lastProgress = 0L
            conn.inputStream.use { input ->
                temp.outputStream().buffered().use { out ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        currentCoroutineContext().ensureActive()
                        val n = input.read(buffer)
                        if (n < 0) break
                        downloaded += n
                        if (downloaded > manifest.sizeBytes) {
                            error("The server sent more data than the pinned model size.")
                        }
                        out.write(buffer, 0, n)
                        digest.update(buffer, 0, n)
                        if (downloaded - lastProgress >= 8L * 1024 * 1024) {
                            _state.value = ModelState.Downloading(manifest, downloaded, manifest.sizeBytes)
                            lastProgress = downloaded
                        }
                    }
                }
            }
            if (downloaded != manifest.sizeBytes) {
                error("Download incomplete: received $downloaded of ${manifest.sizeBytes} bytes.")
            }
            _state.value = ModelState.Verifying(manifest)
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (actual != manifest.artifactSha256) {
                error("Checksum mismatch. The downloaded file is corrupt or not the pinned model.")
            }
            if (!temp.renameTo(target)) {
                temp.copyTo(target, overwrite = true)
                temp.delete()
            }
            _state.value = ModelState.Ready(manifest, loaded = false)
            activeJob = null // allow the explicit load below to start its own job
            loadInstalled()
        } catch (c: CancellationException) {
            temp.delete()
            _state.value = ModelState.NotInstalled
            throw c
        } catch (t: Throwable) {
            temp.delete()
            _state.value = if (cancelRequested) ModelState.NotInstalled
            else ModelState.Failed(manifest, t.message ?: "Download failed.")
        } finally {
            connection = null
            runCatching { conn?.disconnect() }
            cancelRequested = false
        }
    }

    private suspend fun runImport(uri: Uri) = withContext(Dispatchers.IO) {
        val temp = File(installDir, "import.part")
        try {
            runtime.unload()
            temp.delete()
            _state.value = ModelState.Importing

            var displayName = "model"
            var declaredSize: Long? = null
            context.contentResolver.query(
                uri,
                arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE),
                null, null, null
            )?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                    if (nameIndex >= 0 && !cursor.isNull(nameIndex)) displayName = cursor.getString(nameIndex)
                    if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) declaredSize = cursor.getLong(sizeIndex)
                }
            }

            val maxBytes = catalog.maxOf { it.sizeBytes }
            if (declaredSize != null && (declaredSize!! <= 0L || declaredSize!! > maxBytes)) {
                error("This file is not a supported model size.")
            }
            if (!ModelFileVerifier.hasSpaceFor(declaredSize ?: maxBytes, installDir.usableSpace)) {
                error("Not enough free storage for this model plus a 1 GB reserve.")
            }

            val digest = MessageDigest.getInstance("SHA-256")
            var copied = 0L
            val input = context.contentResolver.openInputStream(uri) ?: error("Could not open the selected file.")
            input.use { stream ->
                temp.outputStream().buffered().use { out ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        currentCoroutineContext().ensureActive()
                        val n = stream.read(buffer)
                        if (n < 0) break
                        copied += n
                        if (copied > maxBytes) error("The file is larger than any supported model.")
                        out.write(buffer, 0, n)
                        digest.update(buffer, 0, n)
                    }
                }
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            val matched = catalog.firstOrNull { it.sizeBytes == copied && it.artifactSha256 == actual }
                ?: error("\"$displayName\" does not match a pinned ASHURA model. Only verified .litertlm files can be imported.")
            if (!matched.supports(deviceTier)) {
                error("This model needs a ${matched.minimumTier.label} device; this device is ${deviceTier.label}.")
            }

            deleteOtherModelFiles(matched)
            val target = LiteRtLmModelRuntime.fileFor(installDir, matched)
            if (!temp.renameTo(target)) {
                temp.copyTo(target, overwrite = true)
                temp.delete()
            }
            _state.value = ModelState.Ready(matched, loaded = false)
            activeJob = null // allow the explicit load below to start its own job
            loadInstalled()
        } catch (c: CancellationException) {
            temp.delete()
            _state.value = ModelState.NotInstalled
            throw c
        } catch (t: Throwable) {
            temp.delete()
            _state.value = if (cancelRequested) ModelState.NotInstalled
            else ModelState.Failed(null, t.message ?: "Import failed.")
        } finally {
            cancelRequested = false
        }
    }

    /** One model at a time (spec §6.1): remove other verified files before installing. */
    private fun deleteOtherModelFiles(keep: ModelManifest) {
        catalog.filter { it.id != keep.id }.forEach { other ->
            LiteRtLmModelRuntime.fileFor(installDir, other).delete()
        }
    }

    private fun isOnline(): Boolean {
        val manager = context.getSystemService(ConnectivityManager::class.java) ?: return true
        val network = manager.activeNetwork ?: return false
        val capabilities = manager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    companion object {
        /** Opens the system file picker for a model import. */
        fun importIntent(): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
        }

        fun deviceRamTier(context: Context): RamTier {
            val manager = context.getSystemService(ActivityManager::class.java) ?: return RamTier.CONSTRAINED
            if (manager.isLowRamDevice) return RamTier.CONSTRAINED
            val info = ActivityManager.MemoryInfo()
            manager.getMemoryInfo(info)
            return RamTier.fromTotalBytes(info.totalMem)
        }
    }
}
