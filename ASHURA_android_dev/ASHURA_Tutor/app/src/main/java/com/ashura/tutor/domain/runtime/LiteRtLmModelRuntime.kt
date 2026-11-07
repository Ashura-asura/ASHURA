package com.ashura.tutor.domain.runtime

import com.ashura.tutor.domain.ResponseMode
import com.ashura.tutor.domain.TutorRequest
import com.ashura.tutor.domain.TutorResponse
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.LogSeverity
import com.google.ai.edge.litertlm.RepetitionPenaltyConfig
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.ThinkingConfig
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.io.File
import kotlin.math.max

/**
 * LiteRT-LM adapter for the §6.2 boundary. One engine, one loaded model, CPU by default.
 *
 * The engine applies the model's own chat template, so [generateStream] sends a plain system
 * instruction and user turn from [PromptBuilder.buildParts] rather than a pre-rendered ChatML string.
 * Cancellation calls [Conversation.cancelProcess] before closing the conversation; unloading while
 * a generation is in flight sets a flag that the generation's `finally` honours under the mutex, so
 * native resources are never closed underneath a running decode.
 *
 * Streaming uses `channelFlow` because native chunks are produced on [Dispatchers.Default] while
 * the collector may be on the main thread. Measured timings and heap use are exposed through
 * [metrics] for the Settings diagnostics panel.
 */
class LiteRtLmModelRuntime(
    private val modelsDir: File,
    cacheDir: File,
    private val backendLabel: String = "CPU",
    private val backend: () -> Backend = { Backend.CPU() }
) : ModelRuntime {

    private val mutex = Mutex()
    private val engineCacheDir = File(cacheDir, "litertlm").apply { mkdirs() }

    private val _metrics = MutableStateFlow<RuntimeMetrics?>(null)
    /** Last measured load/generation behaviour for the Settings diagnostics panel. */
    val metrics: StateFlow<RuntimeMetrics?> = _metrics.asStateFlow()

    @Volatile private var engine: Engine? = null
    @Volatile private var loadedManifest: ModelManifest? = null
    @Volatile private var activeConversation: Conversation? = null
    @Volatile private var unloadRequested = false
    @Volatile private var lastError: String? = null

    override val isAvailable: Boolean
        get() = engine?.isInitialized() == true

    override suspend fun load(manifest: ModelManifest, budget: ResourceBudget): LoadResult {
        val problems = manifest.problems()
        if (problems.isNotEmpty()) return LoadResult.Failed("Manifest invalid: ${problems.joinToString("; ")}")

        val file = fileFor(modelsDir, manifest)
        if (!file.isFile) return LoadResult.Failed("The model file is missing. Download or import it again.")
        if (manifest.sizeBytes > 0 && file.length() != manifest.sizeBytes) {
            return LoadResult.Failed(
                "The model file is ${file.length()} bytes but the manifest pins ${manifest.sizeBytes}. " +
                    "It is incomplete or corrupt; download it again."
            )
        }

        // Verification and loading must be one serialised action so a second load cannot swap the
        // file between the checksum and the native read.
        val loadStartedAt = System.nanoTime()
        return mutex.withLock {
            try {
                val verdict = withContext(Dispatchers.IO) {
                    file.inputStream().use { ModelFileVerifier.verify(it, manifest) }
                }
                if (verdict is ModelFileVerifier.Verdict.Invalid) {
                    return@withLock LoadResult.Failed(verdict.reason)
                }

                if (engine != null) closeEngineLocked()

                withContext(Dispatchers.IO) {
                    try {
                        Engine.setNativeMinLogSeverity(LogSeverity.ERROR)
                        val config = EngineConfig(
                            modelPath = file.absolutePath,
                            backend = backend(),
                            maxNumTokens = budget.maxContextTokens,
                            cacheDir = engineCacheDir.absolutePath
                        )
                        val created = Engine(config)
                        created.initialize()
                        engine = created
                        loadedManifest = manifest
                        unloadRequested = false
                        lastError = null
                        _metrics.update {
                            (it ?: RuntimeMetrics(backend = backendLabel)).copy(
                                backend = backendLabel,
                                loadMillis = (System.nanoTime() - loadStartedAt) / 1_000_000,
                                heapUsedMb = heapUsedMb()
                            )
                        }
                        LoadResult.Loaded
                    } catch (c: CancellationException) {
                        throw c
                    } catch (t: Throwable) {
                        // Covers LiteRtLmJniException, UnsatisfiedLinkError and OOM from the native loader.
                        lastError = t.message ?: t.javaClass.simpleName
                        LoadResult.Failed("The model could not be loaded: $lastError")
                    }
                }
            } catch (c: CancellationException) {
                throw c
            } catch (t: Throwable) {
                lastError = t.message ?: t.javaClass.simpleName
                LoadResult.Failed("The model could not be verified: $lastError")
            }
        }
    }

    override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse {
        var response: TutorResponse? = null
        generateStream(request, limits).collect { event ->
            if (event is TutorStreamEvent.Complete) response = event.response
        }
        return response ?: error("The local model returned no answer.")
    }

    override fun generateStream(request: TutorRequest, limits: GenerationLimits): Flow<TutorStreamEvent> = channelFlow {
        val parts = PromptBuilder.buildParts(request, limits)
        mutex.withLock {
            val loaded = loadedManifest
            val current = engine
            check(current != null && loaded != null && current.isInitialized()) {
                "No local model is loaded. Download or import one in Settings, then tap Load."
            }

            val conversation = current.createConversation(
                ConversationConfig(
                    systemInstruction = Contents.of(parts.systemInstruction),
                    maxOutputToken = limits.maxOutputTokens,
                    samplerConfig = SamplerConfig(topK = 40, topP = 0.95, temperature = 0.7),
                    thinkingConfig = if (loaded.disableThinking) ThinkingConfig(enableThinking = false) else null
                )
            )
            activeConversation = conversation
            var completed = false
            val startedAt = System.nanoTime()
            var firstTokenAt = 0L
            var streamedChars = 0
            var chunks = 0
            val raw = StringBuilder()
            try {
                withContext(Dispatchers.Default) {
                    withTimeout(limits.timeoutMillis) {
                        conversation.sendMessageAsync(
                            text = parts.userMessage,
                            repetitionPenaltyConfig = RepetitionPenaltyConfig(repetitionPenalty = 1.05f)
                        ).collect { chunk ->
                            val piece = sanitizeOutput(chunk.contents.toString())
                            raw.append(chunk.contents.toString())
                            if (piece.isNotEmpty()) {
                                if (firstTokenAt == 0L) firstTokenAt = System.nanoTime()
                                chunks++
                                streamedChars += piece.length
                                send(TutorStreamEvent.Delta(piece))
                            }
                        }
                    }
                }
                val cleaned = sanitizeOutput(raw.toString()).trim().take(limits.maxContextCharacters)
                if (cleaned.isEmpty()) error("The model returned an empty answer.")
                val generated = TutorResponse(
                    answer = cleaned,
                    mode = ResponseMode.LOCAL_MODEL,
                    limitation = "Generated by the local model on this device. It can be wrong; " +
                        "check important facts and use the deterministic tools for arithmetic."
                )
                updateMetrics(startedAt, firstTokenAt, System.nanoTime(), streamedChars, chunks)
                send(TutorStreamEvent.Complete(generated))
                completed = true
            } catch (c: CancellationException) {
                throw c
            } catch (t: Throwable) {
                lastError = t.message ?: t.javaClass.simpleName
                throw IllegalStateException("Local generation failed: $lastError", t)
            } finally {
                if (!completed) runCatching { conversation.cancelProcess() }
                runCatching { conversation.close() }
                activeConversation = null
                if (unloadRequested) closeEngineLocked()
            }
        }
    }

    private fun updateMetrics(startedAt: Long, firstTokenAt: Long, finishedAt: Long, chars: Int, chunks: Int) {
        val totalMs = max(1L, (finishedAt - startedAt) / 1_000_000)
        val firstMs = if (firstTokenAt > 0L) (firstTokenAt - startedAt) / 1_000_000 else null
        // This API does not expose exact token ids; ~4 characters/token is the conventional estimate
        // and the UI labels it as approximate.
        val estimated = max(1, chars / 4)
        _metrics.update {
            val base = it ?: RuntimeMetrics(backend = backendLabel)
            base.copy(
                backend = backendLabel,
                firstTokenMillis = firstMs,
                generationMillis = totalMs,
                estimatedTokens = estimated,
                tokensPerSecond = estimated / (totalMs / 1000.0),
                heapUsedMb = heapUsedMb()
            )
        }
    }

    private fun heapUsedMb(): Long {
        val runtime = Runtime.getRuntime()
        return (runtime.totalMemory() - runtime.freeMemory()) / (1024 * 1024)
    }

    override fun unload() {
        unloadRequested = true
        // Ask the native decoder to stop; this is non-suspending and safe to call from the UI thread.
        runCatching { activeConversation?.cancelProcess() }
        if (mutex.tryLock()) {
            try {
                closeEngineLocked()
            } finally {
                mutex.unlock()
            }
        }
        // Otherwise the in-flight generate() closes the engine in its finally block.
    }

    override fun health(): RuntimeHealth {
        val loaded = isAvailable
        val detail = buildString {
            loadedManifest?.let { append("${it.displayName} · ${it.quantization}") }
            if (!loaded) append(if (isEmpty()) "No model loaded" else " (not initialized)")
            lastError?.let { append(" · last error: $it") }
        }
        return RuntimeHealth(loaded = loaded, detail = detail)
    }

    /** Closes the native engine. Must be called while holding [mutex] (or when no decode is active). */
    private fun closeEngineLocked() {
        val current = engine ?: run {
            loadedManifest = null
            unloadRequested = false
            return
        }
        engine = null
        loadedManifest = null
        runCatching { current.close() }
        unloadRequested = false
    }

    private fun sanitizeOutput(raw: String): String =
        raw.replace(Regex("<\\|[^|>]{1,40}\\|>"), "").replace("\u0000", "")

    companion object {
        fun fileName(manifest: ModelManifest): String {
            require(manifest.id.matches(Regex("^[a-z0-9][a-z0-9._-]{2,63}$"))) {
                "Model id is not a safe file name"
            }
            return "${manifest.id}.litertlm"
        }

        fun fileFor(modelsDir: File, manifest: ModelManifest): File = File(modelsDir, fileName(manifest))
    }
}
