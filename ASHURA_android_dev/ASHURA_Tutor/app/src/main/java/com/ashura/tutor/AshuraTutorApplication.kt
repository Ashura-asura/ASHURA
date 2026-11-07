package com.ashura.tutor

import android.app.Application
import com.ashura.tutor.application.PracticeService
import com.ashura.tutor.data.AppDatabase
import com.ashura.tutor.data.DocumentReader
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.domain.CalculatorTool
import com.ashura.tutor.domain.LessonPlanner
import com.ashura.tutor.domain.SpacingScheduler
import com.ashura.tutor.domain.TaskController
import com.ashura.tutor.domain.TutorEngine
import com.ashura.tutor.domain.assessment.AnswerChecker
import com.ashura.tutor.domain.curriculum.CurriculumPack
import com.ashura.tutor.domain.curriculum.SeedCurriculum
import com.ashura.tutor.domain.runtime.ModelRuntime
import com.ashura.tutor.domain.runtime.UnavailableModelRuntime

/** Manual dependency wiring (spec §4.1 modular monolith). One shared [ModelRuntime] instance: never two loaded models. */
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

    override fun onCreate() {
        super.onCreate()
        repository = TutorRepository(AppDatabase.create(this))
        val modelRuntime: ModelRuntime = UnavailableModelRuntime() // swap for a benchmarked runtime (spec §6, §22 Phase 2)
        val calculator = CalculatorTool()
        taskController = TaskController(modelRuntime = modelRuntime, tools = mapOf(calculator.name to calculator))
        tutorEngine = TutorEngine(modelRuntime = modelRuntime, taskController = taskController)
        documentReader = DocumentReader(contentResolver)
        curriculum = SeedCurriculum.pack
        lessonPlanner = LessonPlanner(curriculum)
        spacingScheduler = SpacingScheduler()
        practiceService = PracticeService(repository, AnswerChecker(), spacingScheduler, curriculum)
    }
}
