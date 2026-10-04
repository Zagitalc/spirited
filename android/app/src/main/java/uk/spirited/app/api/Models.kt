package uk.spirited.app.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// These mirror docs/api.md and the response the backend's tests pin. Unknown fields are ignored,
// so the backend can add fields without breaking an installed app.

@Serializable
data class StartPoint(val lat: Double, val lon: Double)

@Serializable
data class LoopRequest(
    val start: StartPoint,
    @SerialName("duration_min") val durationMin: Int,
    val count: Int = 3,
)

/** GeoJSON, so each coordinate is [lon, lat]. */
@Serializable
data class LineString(val coordinates: List<List<Double>>)

@Serializable
data class Shares(
    val recommended: Double,
    @SerialName("not_recommended") val notRecommended: Double,
    @SerialName("built_up") val builtUp: Double,
)

@Serializable
data class Segment(
    @SerialName("from_km") val fromKm: Double,
    @SerialName("to_km") val toKm: Double,
    val road: String,
    /** "recommended", "not_recommended" or "built_up". The backend decides; the app only draws it. */
    val group: String,
    val score: Double? = null,
    val geometry: LineString,
)

@Serializable
data class Loop(
    @SerialName("distance_km") val distanceKm: Double,
    @SerialName("duration_min") val durationMin: Int,
    val score: Double,
    val shares: Shares,
    @SerialName("reuse_share") val reuseShare: Double,
    val geometry: LineString,
    val polyline: String,
    val gpx: String,
    val segments: List<Segment>,
    val warnings: List<String> = emptyList(),
)

@Serializable
data class LoopsResponse(
    val loops: List<Loop>,
    val notes: List<String> = emptyList(),
)

@Serializable
data class Health(val status: String, val version: String = "")
