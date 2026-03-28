package com.escalada.judgeremote

import android.net.Uri
import java.util.Locale

const val EXTRA_JUDGE_URL = "EXTRA_JUDGE_URL"
const val PREFS_NAME = "judge_remote"
const val PREF_LAST_URL = "last_url"

fun normalizeUrl(raw: String): String? {
    val trimmed = raw.trim()
    if (trimmed.isBlank()) return null

    val candidate =
        if (
            trimmed.startsWith("http://", ignoreCase = true) ||
            trimmed.startsWith("https://", ignoreCase = true)
        ) {
            trimmed
        } else {
            "http://$trimmed"
        }

    val parsed = Uri.parse(candidate)
    val scheme = parsed.scheme?.lowercase(Locale.ROOT)
    val host = parsed.host
    return if ((scheme == "http" || scheme == "https") && !host.isNullOrBlank()) {
        candidate
    } else {
        null
    }
}

fun isAcceptableJudgeUrl(raw: String): Boolean = normalizeUrl(raw) != null
