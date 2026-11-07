package com.ashura.tutor

import android.app.Application
import com.ashura.tutor.application.PracticeService
import com.ashura.tutor.data.AppDatabase
import com.ashura.tutor.data.DocumentReader
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.data.StudyPackRepository
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
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
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
    lateinit var studyPacks: StudyPackRepository
        private set

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()
        // PdfBox-Android needs its bundled font/metric resources before the first PDF is opened.
        PDFBoxResourceLoader.init(this)
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
        // Keep the verified model ready across app restarts. The user can still unload it explicitly;
        // nothing unloads it behind their back.
        appScope.launch { modelManager.autoLoadInstalled() }
        learnerProfile = LearnerProfileStore(this)
        studyPacks = StudyPackRepository(assets)
        val calculator = CalculatorTool()
        taskController = TaskController(modelRuntime = modelRuntime, tools = mapOf(calculator.name to calculator))
        tutorEngine = TutorEngine(modelRuntime = modelRuntime, taskController = taskController)
        documentReader = DocumentReader(contentResolver, cacheDir)
        curriculum = SeedCurriculum.pack
        lessonPlanner = LessonPlanner(curriculum)
        spacingScheduler = SpacingScheduler()
        practiceService = PracticeService(repository, AnswerChecker(), spacingScheduler, curriculum)
    }

    /**
     * The model is never unloaded automatically. Earlier builds unloaded on memory-pressure callbacks,
     * which surprised learners in the middle of a session. The user now controls load/unload explicitly
     * from Settings; the operating system can still reclaim the process if it needs the memory.
     */
}
