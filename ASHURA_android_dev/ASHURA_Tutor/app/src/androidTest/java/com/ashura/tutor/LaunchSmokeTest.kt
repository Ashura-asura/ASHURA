package com.ashura.tutor

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.ActivityTestRule
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LaunchSmokeTest {
    @get:Rule val activityRule = ActivityTestRule(MainActivity::class.java)

    @Test fun activityLaunches() {
        assertFalse(activityRule.activity.isFinishing)
    }
}
