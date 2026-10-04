package uk.spirited.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BackendSettingsTest {
    @Test
    fun `a bare address gets http and loses a trailing slash`() {
        assertEquals("http://192.168.50.10:8000", BackendSettings.normalise(" 192.168.50.10:8000/ "))
    }

    @Test
    fun `a full address is kept`() {
        assertEquals("https://example.org", BackendSettings.normalise("https://example.org"))
    }

    @Test
    fun `nothing useful is refused`() {
        assertNull(BackendSettings.normalise("   "))
        assertNull(BackendSettings.normalise("http://"))
    }
}
