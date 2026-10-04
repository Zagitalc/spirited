package uk.spirited.app.map

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Card
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.Point
import uk.spirited.app.LoopsPanel
import uk.spirited.app.LoopsState
import uk.spirited.app.MapViewModel
import uk.spirited.app.SettingsSheet

private const val START_SOURCE = "start-source"
private const val START_LAYER = "start-layer"
private const val LOOP_SOURCE = "loop-source"
private const val LOOP_CASING = "loop-casing"
private const val LOOP_LINE = "loop-line"

private fun colourByGroup(): Expression =
    Expression.match(
        Expression.get(LoopStyle.GROUP),
        Expression.color(LoopStyle.colourOf("")),
        Expression.stop("recommended", Expression.color(LoopStyle.colourOf("recommended"))),
        Expression.stop("not_recommended", Expression.color(LoopStyle.colourOf("not_recommended"))),
        Expression.stop("built_up", Expression.color(LoopStyle.colourOf("built_up"))),
    )

/** A point on the map, kept as plain numbers so it survives rotation. */
data class Position(
    val lat: Double,
    val lon: Double,
)

private val CameraSaver =
    listSaver<CameraPosition?, Double>(
        save = { c -> if (c == null) emptyList() else listOf(c.target!!.latitude, c.target!!.longitude, c.zoom) },
        restore = { l ->
            if (l.size == 3) {
                CameraPosition
                    .Builder()
                    .target(LatLng(l[0], l[1]))
                    .zoom(l[2])
                    .build()
            } else {
                null
            }
        },
    )

/**
 * The map, the start marker and the controls under it. Long-press puts the start where the finger is.
 * The map sits above the panel, not behind it, so the attribution button and logo that MapLibre
 * draws stay visible: the map data licence needs them.
 */
@Composable
fun MapScreen(
    viewModel: MapViewModel,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val mapView = remember { MapView(context) }

    val start = viewModel.start
    var camera by rememberSaveable(stateSaver = CameraSaver) { mutableStateOf<CameraPosition?>(null) }
    var map by remember { mutableStateOf<MapLibreMap?>(null) }
    var styleReady by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    var permissionBlocked by remember { mutableStateOf(false) }
    var locating by remember { mutableStateOf(false) }
    var showSettings by remember { mutableStateOf(false) }

    fun locate() {
        locating = true
        message = "Finding your location..."
        LocationFetcher.getOnce(context) { result ->
            locating = false
            when (result) {
                is LocationFetcher.Result.Found -> {
                    viewModel.chooseStart(result.position)
                    message = null
                    map?.animateCamera(
                        CameraUpdateFactory.newLatLngZoom(LatLng(result.position.lat, result.position.lon), 12.0),
                    )
                }
                LocationFetcher.Result.Unavailable ->
                    message = "Location is switched off. Turn it on in the phone's settings, or long-press the map."
                LocationFetcher.Result.NoFix ->
                    message = "Could not get a location fix. Try again, or long-press the map."
            }
        }
    }

    val permissionLauncher =
        rememberLauncherForActivityResult(
            ActivityResultContracts.RequestMultiplePermissions(),
        ) { granted ->
            if (granted.values.any { it }) {
                permissionBlocked = false
                locate()
            } else {
                // After a refusal Android may stop showing the prompt, so the way back is the app's settings page.
                permissionBlocked = true
                message = "Location permission is off. Allow it in the app's settings, or long-press the map."
            }
        }

    DisposableEffect(lifecycle, mapView) {
        val observer =
            LifecycleEventObserver { _, event ->
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
                ?: CameraPosition
                    .Builder()
                    .target(LatLng(MapConfig.INITIAL_LAT, MapConfig.INITIAL_LON))
                    .zoom(MapConfig.INITIAL_ZOOM)
                    .build()
            m.addOnCameraIdleListener { camera = m.cameraPosition }
            m.addOnMapLongClickListener { point ->
                viewModel.chooseStart(Position(point.latitude, point.longitude))
                message = null
                true
            }
            m.setStyle(MapConfig.STYLE_URL) { style ->
                // The loop goes in first so the start marker is drawn on top of it.
                style.addSource(GeoJsonSource(LOOP_SOURCE))
                style.addLayer(
                    LineLayer(LOOP_CASING, LOOP_SOURCE).withProperties(
                        lineColor("#ffffff"),
                        lineWidth(9f),
                        lineCap(Property.LINE_CAP_ROUND),
                        lineJoin(Property.LINE_JOIN_ROUND),
                    ),
                )
                style.addLayer(
                    LineLayer(LOOP_LINE, LOOP_SOURCE).withProperties(
                        lineColor(colourByGroup()),
                        lineWidth(5f),
                        lineCap(Property.LINE_CAP_ROUND),
                        lineJoin(Property.LINE_JOIN_ROUND),
                    ),
                )
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
        if (start == null) {
            source.setGeoJson(FeatureCollection.fromFeatures(emptyList<Feature>()))
        } else {
            source.setGeoJson(Feature.fromGeometry(Point.fromLngLat(start.lon, start.lat)))
        }
    }

    // Draw the chosen loop. The map is fitted to it only when the person has just chosen or
    // received one; after a rotation the saved camera stays.
    val state = viewModel.loops
    val shown = (state as? LoopsState.Loaded)?.response?.loops?.getOrNull(viewModel.selectedLoop)
    var fitted by rememberSaveable { mutableStateOf(0) }
    LaunchedEffect(map, styleReady, shown) {
        val style = map?.style ?: return@LaunchedEffect
        if (!styleReady) return@LaunchedEffect
        val source = style.getSourceAs<GeoJsonSource>(LOOP_SOURCE) ?: return@LaunchedEffect
        if (shown == null) {
            source.setGeoJson(FeatureCollection.fromFeatures(emptyList<Feature>()))
        } else {
            source.setGeoJson(LoopStyle.features(shown))
            val points = shown.geometry.coordinates.map { LatLng(it[1], it[0]) }
            if (points.size >= 2 && viewModel.fitCount != fitted) {
                fitted = viewModel.fitCount
                val bounds = LatLngBounds.Builder().includes(points).build()
                map?.animateCamera(CameraUpdateFactory.newLatLngBounds(bounds, 80))
            }
        }
    }

    val mapBox: @Composable (Modifier) -> Unit = { boxModifier ->
        Box(modifier = boxModifier) {
            AndroidView(factory = { mapView }, modifier = Modifier.fillMaxSize())
            Row(
                modifier =
                    Modifier
                        .align(Alignment.TopCenter)
                        .statusBarsPadding()
                        .padding(12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Card(modifier = Modifier.weight(1f, fill = false)) {
                    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) {
                        val text =
                            message
                                ?: start?.let { "Start: %.4f, %.4f".format(it.lat, it.lon) }
                                ?: "Long-press the map to choose where to start"
                        Text(text = text, style = MaterialTheme.typography.bodyMedium)
                        if (permissionBlocked) {
                            TextButton(onClick = {
                                context.startActivity(
                                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                                        .setData(Uri.fromParts("package", context.packageName, null)),
                                )
                            }) { Text("Open settings") }
                        }
                    }
                }
                Card { TextButton(onClick = { showSettings = true }) { Text("Backend") } }
            }
            ExtendedFloatingActionButton(
                onClick = {
                    val permissions =
                        arrayOf(
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION,
                        )
                    val granted =
                        permissions.any {
                            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
                        }
                    if (granted) {
                        permissionBlocked = false
                        if (!locating) locate()
                    } else {
                        permissionLauncher.launch(permissions)
                    }
                },
                modifier =
                    Modifier
                        .align(Alignment.BottomEnd)
                        .padding(16.dp),
            ) {
                Text("Use my location")
            }
        }
    }

    // Beside the map when the phone is on its side, under it otherwise, so the map never
    // shrinks to a strip.
    if (LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE) {
        Row(modifier = modifier.fillMaxSize()) {
            mapBox(Modifier.weight(1f).fillMaxHeight())
            LoopsPanel(viewModel, Modifier.width(360.dp).fillMaxHeight(), maxHeight = Dp.Infinity)
        }
    } else {
        Column(modifier = modifier.fillMaxSize()) {
            mapBox(Modifier.weight(1f).fillMaxWidth())
            LoopsPanel(viewModel)
        }
    }

    if (showSettings) {
        SettingsSheet(viewModel, onDismiss = { showSettings = false })
    }
}
