package uk.spirited.app.map

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.Point

private const val START_SOURCE = "start-source"
private const val START_LAYER = "start-layer"

/** A point on the map, kept as plain numbers so it survives rotation. */
data class Position(val lat: Double, val lon: Double)

private val PositionSaver = listSaver<Position?, Double>(
    save = { p -> if (p == null) emptyList() else listOf(p.lat, p.lon) },
    restore = { l -> if (l.size == 2) Position(l[0], l[1]) else null },
)

private val CameraSaver = listSaver<CameraPosition?, Double>(
    save = { c -> if (c == null) emptyList() else listOf(c.target!!.latitude, c.target!!.longitude, c.zoom) },
    restore = { l ->
        if (l.size == 3) CameraPosition.Builder().target(LatLng(l[0], l[1])).zoom(l[2]).build() else null
    },
)

/**
 * The map with a single start marker. Long-press puts the start where the finger is.
 * The attribution button and logo that MapLibre draws are left on: the map data licence needs them.
 */
@Composable
fun MapScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val mapView = remember { MapView(context) }

    var start by rememberSaveable(stateSaver = PositionSaver) { mutableStateOf<Position?>(null) }
    var camera by rememberSaveable(stateSaver = CameraSaver) { mutableStateOf<CameraPosition?>(null) }
    var map by remember { mutableStateOf<MapLibreMap?>(null) }
    var styleReady by remember { mutableStateOf(false) }

    DisposableEffect(lifecycle, mapView) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_CREATE -> mapView.onCreate(null)
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                Lifecycle.Event.ON_DESTROY -> mapView.onDestroy()
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            // If the activity is going away its own ON_DESTROY has already been delivered.
            if (lifecycle.currentState != Lifecycle.State.DESTROYED) {
                mapView.onPause()
                mapView.onStop()
                mapView.onDestroy()
            }
        }
    }

    LaunchedEffect(mapView) {
        mapView.getMapAsync { m ->
            m.cameraPosition = camera
                ?: CameraPosition.Builder()
                    .target(LatLng(MapConfig.INITIAL_LAT, MapConfig.INITIAL_LON))
                    .zoom(MapConfig.INITIAL_ZOOM)
                    .build()
            m.addOnCameraIdleListener { camera = m.cameraPosition }
            m.addOnMapLongClickListener { point ->
                start = Position(point.latitude, point.longitude)
                true
            }
            m.setStyle(MapConfig.STYLE_URL) { style ->
                style.addSource(GeoJsonSource(START_SOURCE))
                style.addLayer(
                    CircleLayer(START_LAYER, START_SOURCE).withProperties(
                        circleRadius(9f),
                        circleColor("#d32f2f"),
                        circleStrokeColor("#ffffff"),
                        circleStrokeWidth(3f),
                    ),
                )
                styleReady = true
            }
            map = m
        }
    }

    // Redraw the marker whenever the start changes or the style finishes loading.
    LaunchedEffect(map, styleReady, start) {
        val style = map?.style ?: return@LaunchedEffect
        if (!styleReady) return@LaunchedEffect
        val source = style.getSourceAs<GeoJsonSource>(START_SOURCE) ?: return@LaunchedEffect
        val here = start
        if (here == null) {
            source.setGeoJson(FeatureCollection.fromFeatures(emptyList<Feature>()))
        } else {
            source.setGeoJson(Feature.fromGeometry(Point.fromLngLat(here.lon, here.lat)))
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        AndroidView(factory = { mapView }, modifier = Modifier.fillMaxSize())
        Card(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .safeDrawingPadding()
                .padding(12.dp),
        ) {
            val text = start?.let { "Start: %.4f, %.4f".format(it.lat, it.lon) }
                ?: "Long-press the map to choose where to start"
            Text(
                text = text,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            )
        }
    }
}
