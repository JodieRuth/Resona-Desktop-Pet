package com.resona.client

import android.content.Context

object ResonaPrefs {
    private const val PREFS = "resona_client_prefs"
    private const val KEY_BASE_URL = "base_url"
    private const val KEY_SESSION_ID = "session_id"

    fun getBaseUrl(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_BASE_URL, "") ?: ""
    }

    fun saveBaseUrl(context: Context, url: String) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_BASE_URL, url).apply()
    }

    fun getSessionId(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_SESSION_ID, "") ?: ""
    }

    fun saveSessionId(context: Context, id: String) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_SESSION_ID, id).apply()
    }
}
