package uk.spirited.app.map

import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.LineString
import org.maplibre.geojson.Point
import uk.spirited.app.api.Loop

/**
 * How a loop is drawn. The app never decides what kind of road a stretch is: the backend says
 * which group each segment is in, and this only turns a group into a colour.
 */
object LoopStyle {
    const val GROUP = "group"

    const val RECOMMENDED = 0xFF2E7D32.toInt()
    const val NOT_RECOMMENDED = 0xFFEF6C00.toInt()
    const val BUILT_UP = 0xFF757575.toInt()

    /** Anything the backend adds later is drawn grey until the app learns about it. */
    fun colourOf(group: String): Int = when (group) {
        "recommended" -> RECOMMENDED
        "not_recommended" -> NOT_RECOMMENDED
        else -> BUILT_UP
    }

    /** One line feature per segment, tagged with its group, in driving order. */
    fun features(loop: Loop): FeatureCollection = FeatureCollection.fromFeatures(
        loop.segments.map { segment ->
            // GeoJSON coordinates are [lon, lat].
            val line = LineString.fromLngLats(segment.geometry.coordinates.map { Point.fromLngLat(it[0], it[1]) })
            Feature.fromGeometry(line).also { it.addStringProperty(GROUP, segment.group) }
        },
    )
}
