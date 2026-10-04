package uk.spirited.app

import android.content.Context
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** Where the backend lives. Not a secret: a computer's address on the local network. */
class BackendSettings(context: Context) {
    private val prefs = context.getSharedPreferences("spirited", Context.MODE_PRIVATE)

    var url: String
        get() = prefs.getString(KEY, DEFAULT_URL) ?: DEFAULT_URL
        set(value) = prefs.edit().putString(KEY, value).apply()

    companion object {
        private const val KEY = "backend_url"

        /** The Android emulator's name for the computer it runs on. */
        const val DEFAULT_URL = "http://10.0.2.2:8000"

        /** Tidies what a person typed, or returns null if it cannot be an address. */
        fun normalise(text: String): String? {
            val trimmed = text.trim().trimEnd('/')
            if (trimmed.isEmpty()) return null
            val withScheme = if ("://" in trimmed) trimmed else "http://$trimmed"
            return withScheme.takeIf { it.toHttpUrlOrNull() != null }
        }
    }
}
