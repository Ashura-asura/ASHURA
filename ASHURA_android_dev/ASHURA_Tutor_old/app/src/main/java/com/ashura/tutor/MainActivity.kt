package com.ashura.tutor

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Surface
import androidx.lifecycle.viewmodel.compose.viewModel
import com.ashura.tutor.ui.AshuraTutorApp
import com.ashura.tutor.ui.TutorViewModel
import com.ashura.tutor.ui.TutorViewModelFactory
import com.ashura.tutor.ui.theme.AshuraTutorTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as AshuraTutorApplication
        setContent {
            AshuraTutorTheme {
                Surface {
                    val vm: TutorViewModel = viewModel(
                        factory = TutorViewModelFactory(
                            app.repository, app.tutorEngine, app.lessonPlanner, app.spacingScheduler
                        )
                    )
                    AshuraTutorApp(vm)
                }
            }
        }
    }
}
