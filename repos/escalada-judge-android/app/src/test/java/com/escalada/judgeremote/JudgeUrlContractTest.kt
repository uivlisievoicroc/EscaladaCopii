package com.escalada.judgeremote

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JudgeUrlContractTest {
    @Test
    fun acceptsPrivateLanHostsAndLocalNames() {
        assertEquals("http://192.168.1.50:8000/#/judge/0", normalizeUrl("192.168.1.50:8000/#/judge/0"))
        assertTrue(isAcceptableJudgeUrl("http://10.0.0.5:8000/#/judge/1"))
        assertTrue(isAcceptableJudgeUrl("http://172.16.0.10:8000/#/judge/2"))
        assertTrue(isAcceptableJudgeUrl("http://localhost:8000/#/judge/0"))
        assertTrue(isAcceptableJudgeUrl("http://escalada.local:8000/#/judge/0"))
    }

    @Test
    fun rejectsPublicHostsAndDangerousSchemes() {
        assertFalse(isAcceptableJudgeUrl("https://example.com/#/judge/0"))
        assertFalse(isAcceptableJudgeUrl("http://8.8.8.8:8000/#/judge/0"))
        assertFalse(isAcceptableJudgeUrl("javascript:alert(1)"))
        assertFalse(isAcceptableJudgeUrl("file:///sdcard/index.html"))
    }
}
