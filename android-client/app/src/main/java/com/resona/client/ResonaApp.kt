package com.resona.client

import android.app.Application
import android.content.Intent

class ResonaApp : Application() {
    override fun onCreate() {
        super.onCreate()
        ForegroundTracker.init(this)
        fun reportCrash(e: Throwable) {
            val summary = "${e::class.java.simpleName}: ${e.message ?: "unknown"}"
            try {
                val intent = Intent(ResonaService.ACTION_ERROR).apply {
                    putExtra(ResonaService.EXTRA_TEXT, "崩溃：$summary")
                }
                sendBroadcast(intent)
            } catch (_: Throwable) {
            }
        }

        Thread.setDefaultUncaughtExceptionHandler { _, e ->
            reportCrash(e)
        }
    }
}
