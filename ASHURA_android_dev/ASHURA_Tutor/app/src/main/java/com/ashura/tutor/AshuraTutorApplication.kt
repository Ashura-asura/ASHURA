package com.ashura.tutor

import android.app.Application
import android.content.ComponentCallbacks2
import com.ashura.tutor.application.PracticeService
import com.ashura.tutor.data.AppDatabase
import com.ashura.tutor.data.DocumentReader
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.data.model.ModelManager
import com.ashura.tutor.data.profile.LearnerProfileStore
import com.ashura.tutor.domain.CalculatorTool
import com.ashura.tutor.domain.LessonPlanner
import com.ashura.tutor.domain.SpacingScheduler
import com.ashura.tutor.domain.TaskController
import com.ashura.tutor.domain.TutorEngine
import com.ashura.tutor.domain.assessment.AnswerChecker
import com.ashura.tutor.domain.curriculum.CurriculumPack
import com.ashura.tutor.domain.curriculum.SeedCurriculum
import com.ashura.tutor.domain.runtime.LiteRtLmModelRuntime
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import java.io.File

/** Manual dependency wiring (spec §4.1 modular monolith). One shared runtime instance: never two loaded models. */
class AshuraTutorApplication : Application() {
    lateinit var repository: TutorRepository
        private set
    lateinit var tutorEngine: TutorEngine
        private set
    lateinit var taskController: TaskController
        private set
    lateinit var lessonPlanner: LessonPlanner
        private set
    lateinit var spacingScheduler: SpacingScheduler
        private set
    lateinit var practiceService: PracticeService
        private set
    lateinit var curriculum: CurriculumPack
        private set
    lateinit var documentReader: DocumentReader
        private set
    lateinit var modelManager: ModelManager
        private set
    lateinit var modelRuntime: LiteRtLmModelRuntime
        private set
    lateinit var learnerProfile: LearnerProfileStore
        private set

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()
        repository = TutorRepository(AppDatabase.create(this))
        modelRuntime = LiteRtLmModelRuntime(
            modelsDir = File(filesDir, "models"),
            cacheDir = cacheDir
        )
        modelManager = ModelManager(
            context = this,
            runtime = modelRuntime,
            scope = appScope
        )
        learnerProfile = LearnerProfileStore(this)
        val calculator = CalculatorTool()
        taskController = TaskController(modelRuntime = modelRuntime, tools = mapOf(calculator.name to calculator))
        tutorEngine = TutorEngine(modelRuntime = modelRuntime, taskController = taskController)
        documentReader = DocumentReader(contentResolver)
        curriculum = SeedCurriculum.pack
        lessonPlanner = LessonPlanner(curriculum)
        spacingScheduler = SpacingScheduler()
        practiceService = PracticeService(repository, AnswerChecker(), spacingScheduler, curriculum)
    }

    /**
     * Frees the model's memory when the process is under pressure (spec §16.4). The file stays installed;
     * the user can load it again from Settings. ModelManager.unload() is non-suspending and cancels an
     * in-flight decode before releasing the native engine.
     */
    @Suppress("DEPRECATION")
    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        val critical = level == ComponentCallbacks2.TRIM_MEMORY_RUNNING_CRITICAL ||
            level >= ComponentCallbacks2.TRIM_MEMORY_MODERATE
        if (critical && ::modelManager.isInitialized) modelManager.unload()
    }
}
