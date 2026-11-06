package com.ashura.tutor

import android.app.Application
import com.ashura.tutor.domain.CalculatorTool
import com.ashura.tutor.data.AppDatabase
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.domain.LessonPlanner
import com.ashura.tutor.domain.SpacingScheduler
import com.ashura.tutor.domain.TaskController
import com.ashura.tutor.domain.TutorEngine
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
        taskController = TaskController(
            modelRuntime = UnavailableModelRuntime(),
            tools = mapOf(calculator.name to calculator)
        )
        tutorEngine = TutorEngine(
            modelRuntime = UnavailableModelRuntime(),
            taskController = taskController
        )
        lessonPlanner = LessonPlanner()
        spacingScheduler = SpacingScheduler()
    }
}
