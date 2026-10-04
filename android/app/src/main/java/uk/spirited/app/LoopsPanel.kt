package uk.spirited.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

/** Drive time, the Find loops button and what came back. Step 6 replaces the text with cards on the map. */
@Composable
fun LoopsPanel(viewModel: MapViewModel, modifier: Modifier = Modifier) {
    Surface(modifier = modifier.fillMaxWidth(), tonalElevation = 3.dp) {
        Column(
            modifier = Modifier.navigationBarsPadding().padding(16.dp),
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
                    }
                    loops.forEachIndexed { index, loop ->
                        Text(
                            "${index + 1}. %.1f km, about %d min, score %.0f".format(
                                loop.distanceKm,
                                loop.durationMin,
                                loop.score,
                            ),
                            style = MaterialTheme.typography.bodyMedium,
                        )
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
