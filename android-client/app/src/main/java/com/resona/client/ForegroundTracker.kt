package com.resona.client

import android.app.Activity
import android.app.Application
import android.os.Bundle
import java.util.concurrent.atomic.AtomicBoolean

object ForegroundTracker {
    private val startedCount = java.util.concurrent.atomic.AtomicInteger(0)
    private val foreground = AtomicBoolean(false)

    fun init(app: Application) {
        app.registerActivityLifecycleCallbacks(object : Application.ActivityLifecycleCallbacks {
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {}
            override fun onActivityStarted(activity: Activity) {
                if (startedCount.incrementAndGet() > 0) {
                    foreground.set(true)
                }
            }
            override fun onActivityResumed(activity: Activity) {}
            override fun onActivityPaused(activity: Activity) {}
            override fun onActivityStopped(activity: Activity) {
                if (startedCount.decrementAndGet() <= 0) {
                    foreground.set(false)
                }
            }
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}
            override fun onActivityDestroyed(activity: Activity) {}
        })
    }

    fun isForeground(): Boolean = foreground.get()
}
