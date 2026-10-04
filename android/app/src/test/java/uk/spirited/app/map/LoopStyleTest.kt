package uk.spirited.app.map

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import uk.spirited.app.api.LineString
import uk.spirited.app.api.Loop
import uk.spirited.app.api.Segment
import uk.spirited.app.api.Shares

class LoopStyleTest {
    private fun segment(group: String, vararg points: List<Double>) =
        Segment(0.0, 1.0, "road", group, null, LineString(points.toList()))

    private val loop = Loop(
        distanceKm = 10.0,
        durationMin = 20,
        score = 50.0,
        shares = Shares(0.5, 0.25, 0.25),
        reuseShare = 0.0,
        geometry = LineString(listOf(listOf(-1.0, 51.0), listOf(-1.1, 51.1))),
        polyline = "",
        gpx = "",
        segments = listOf(
            segment("recommended", listOf(-1.0, 51.0), listOf(-1.1, 51.1)),
            segment("built_up", listOf(-1.1, 51.1), listOf(-1.2, 51.2)),
            segment("not_recommended", listOf(-1.2, 51.2), listOf(-1.3, 51.3)),
        ),
    )

    @Test
    fun `each segment becomes one feature carrying the backend's group, in order`() {
        val features = LoopStyle.features(loop).features()!!
        assertEquals(listOf("recommended", "built_up", "not_recommended"), features.map { it.getStringProperty("group") })
    }

    @Test
    fun `coordinates are read as lon then lat`() {
        val line = LoopStyle.features(loop).features()!![0].geometry() as org.maplibre.geojson.LineString
        assertEquals(-1.0, line.coordinates()[0].longitude(), 0.0)
        assertEquals(51.0, line.coordinates()[0].latitude(), 0.0)
    }

    @Test
    fun `each group has its own colour and an unknown one is drawn as built up`() {
        val colours = listOf("recommended", "not_recommended", "built_up").map(LoopStyle::colourOf)
        assertEquals(3, colours.toSet().size)
        assertNotEquals(LoopStyle.colourOf("recommended"), LoopStyle.colourOf("not_recommended"))
        assertEquals(LoopStyle.colourOf("built_up"), LoopStyle.colourOf("anything new"))
    }
}
