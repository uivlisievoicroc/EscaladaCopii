package com.escalada.judgeremote

import java.net.URI
import java.util.Locale

const val EXTRA_JUDGE_URL = "EXTRA_JUDGE_URL"
const val PREFS_NAME = "judge_remote"
const val PREF_LAST_URL = "last_url"

private val SCHEME_PATTERN = Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:")
private val IPV4_PATTERN = Regex("^\\d{1,3}(?:\\.\\d{1,3}){3}$")

fun normalizeUrl(raw: String): String? {
    val trimmed = raw.trim()
    if (trimmed.isBlank()) return null

    val hasScheme = SCHEME_PATTERN.containsMatchIn(trimmed)
    if (
        hasScheme &&
            !trimmed.startsWith("http://", ignoreCase = true) &&
            !trimmed.startsWith("https://", ignoreCase = true)
    ) {
        return null
    }

    val candidate =
        if (
            trimmed.startsWith("http://", ignoreCase = true) ||
            trimmed.startsWith("https://", ignoreCase = true)
        ) {
            trimmed
        } else {
            "http://$trimmed"
        }

    val parsed =
        try {
            URI(candidate)
        } catch (_: Exception) {
            return null
        }
    val scheme = parsed.scheme?.lowercase(Locale.ROOT)
    val host = parsed.host
    return if (
        (scheme == "http" || scheme == "https") &&
            !host.isNullOrBlank() &&
            isAllowedJudgeHost(host)
    ) {
        candidate
    } else {
        null
    }
}

fun isAcceptableJudgeUrl(raw: String): Boolean = normalizeUrl(raw) != null

private fun isAllowedJudgeHost(host: String): Boolean {
    val normalized = host.trim().trim('[', ']').trimEnd('.').lowercase(Locale.ROOT)
    if (normalized == "localhost" || normalized.endsWith(".local")) return true
    if (normalized == "::1" || normalized == "0:0:0:0:0:0:0:1") return true
    if (isConfiguredAllowedHost(normalized)) return true
    return isPrivateIpv4(normalized) || isPrivateIpv6(normalized)
}

private fun isConfiguredAllowedHost(host: String): Boolean {
    return BuildConfig.ALLOWED_JUDGE_HOSTS
        .split(',')
        .asSequence()
        .map { it.trim().trimEnd('.').lowercase(Locale.ROOT) }
        .filter { it.isNotBlank() }
        .any { it == host }
}

private fun isPrivateIpv4(host: String): Boolean {
    if (!IPV4_PATTERN.matches(host)) return false
    val parts = host.split('.').mapNotNull { it.toIntOrNull() }
    if (parts.size != 4 || parts.any { it !in 0..255 }) return false
    val first = parts[0]
    val second = parts[1]
    return first == 10 ||
        first == 127 ||
        (first == 172 && second in 16..31) ||
        (first == 192 && second == 168) ||
        (first == 169 && second == 254)
}

private fun isPrivateIpv6(host: String): Boolean {
    return host.startsWith("fc") ||
        host.startsWith("fd") ||
        host.startsWith("fe80:")
}
