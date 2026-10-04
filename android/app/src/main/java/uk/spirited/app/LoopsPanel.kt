package uk.spirited.app

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import uk.spirited.app.api.Loop
import uk.spirited.app.map.LoopStyle
import kotlin.math.roundToInt

/** Drive time, the Find loops button, and the loops that came back as cards to choose between. */
@Composable
fun LoopsPanel(viewModel: MapViewModel, modifier: Modifier = Modifier) {
    Surface(modifier = modifier.fillMaxWidth(), tonalElevation = 3.dp) {
        Column(
            modifier = Modifier
                // Long notes scroll instead of squeezing the map away.
                .heightIn(max = 340.dp)
                .verticalScroll(rememberScrollState())
                .navigationBarsPadding()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Drive time: ${formatMinutes(viewModel.minutes)}", style = MaterialTheme.typography.titleSmall)
            Slider(
                value = viewModel.minutes.toFloat(),
                onValueChange = { viewModel.chooseMinutes((it / STEP).roundToInt() * STEP) },
                valueRange = MapViewModel.MIN_MINUTES.toFloat()..MapViewModel.MAX_MINUTES.toFloat(),
                // 20 to 240 in steps of 5 has 43 positions between the ends.
                steps = (MapViewModel.MAX_MINUTES - MapViewModel.MIN_MINUTES) / STEP - 1,
            )
            val loading = viewModel.loops is LoopsState.Loading
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(
                    onClick = viewModel::requestLoops,
                    enabled = viewModel.start != null && !loading,
                ) {
                    Text("Find loops")
                }
                when {
                    loading -> {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 3.dp)
                        Text("Planning drives...", style = MaterialTheme.typography.bodyMedium)
                    }
                    viewModel.start == null ->
                        Text("Choose a start first.", style = MaterialTheme.typography.bodyMedium)
                }
            }
            when (val state = viewModel.loops) {
                is LoopsState.Error ->
                    Text(state.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
                is LoopsState.Loaded -> {
                    val loops = state.response.loops
                    if (loops.isEmpty()) {
                        Text("No loop passed the checks from here.", style = MaterialTheme.typography.bodyMedium)
                    } else {
                        LoopCards(loops, viewModel.selectedLoop, viewModel::chooseLoop)
                        Legend()
                        loops.getOrNull(viewModel.selectedLoop)?.warnings?.forEach {
                            Text(it, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    state.response.notes.forEach {
                        Text(it, style = MaterialTheme.typography.bodySmall)
                    }
                }
                else -> Unit
            }
        }
    }
}

private const val STEP = 5

private fun formatMinutes(minutes: Int): String =
    if (minutes < 60) "$minutes min" else "${minutes / 60} h ${"%02d".format(minutes % 60)} min"

@Composable
private fun LoopCards(loops: List<Loop>, selected: Int, onSelect: (Int) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        loops.forEachIndexed { index, loop ->
            val colours = if (index == selected) {
                CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
            } else {
                CardDefaults.cardColors()
            }
            Card(
                modifier = Modifier.weight(1f).clickable { onSelect(index) },
                colors = colours,
            ) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Text("Loop ${index + 1}", style = MaterialTheme.typography.titleSmall)
                    Text("%.0f km".format(loop.distanceKm), style = MaterialTheme.typography.bodyMedium)
                    Text("about ${loop.durationMin} min", style = MaterialTheme.typography.bodySmall)
                    Text("score %.0f".format(loop.score), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun Legend() {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        LegendItem(LoopStyle.RECOMMENDED, "recommended")
        LegendItem(LoopStyle.NOT_RECOMMENDED, "cannot vouch for")
        LegendItem(LoopStyle.BUILT_UP, "built up")
    }
}

@Composable
private fun LegendItem(colour: Int, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(modifier = Modifier.size(10.dp).background(Color(colour), CircleShape))
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}
