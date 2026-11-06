package com.ashura.tutor

import android.app.Application
import com.ashura.tutor.data.AppDatabase
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.domain.CalculatorTool
import com.ashura.tutor.domain.LessonPlanner
import com.ashura.tutor.domain.SpacingScheduler
import com.ashura.tutor.domain.TaskController
import com.ashura.tutor.domain.TutorEngine
import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.UnavailableModelRuntime

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

    override fun onCreate() {
        super.onCreate()
        repository = TutorRepository(AppDatabase.create(this))
        val calculator = CalculatorTool()
        // One owner/instance for the runtime lifecycle. Replace this factory
        // with the measured Android backend when that implementation exists.
        val modelRuntime = UnavailableModelRuntime()
        val limits = GenerationLimits()
        taskController = TaskController(
            modelRuntime = modelRuntime,
            tools = mapOf(calculator.name to calculator),
            limits = limits
        )
        tutorEngine = TutorEngine(
            modelRuntime = modelRuntime,
            taskController = taskController,
            limits = limits
        )
        lessonPlanner = LessonPlanner()
        spacingScheduler = SpacingScheduler()
    }
}
