package uk.spirited.app

import org.junit.Assert.assertEquals
import org.junit.Test

class GpxShareTest {
    @Test
    fun `the file name says which loop and how long, with nothing a file system dislikes`() {
        assertEquals("spirited-loop-2-84min.gpx", GpxShare.fileName(2, 84))
    }
}
