package uk.spirited.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Where the backend is, with a way to check it answers. For development until Stage 5 hosts it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsSheet(viewModel: MapViewModel, onDismiss: () -> Unit) {
    var text by remember { mutableStateOf(viewModel.backendUrl) }
    ModalBottomSheet(onDismissRequest = {
        viewModel.clearConnectionMessage()
        onDismiss()
    }) {
        Column(
            modifier = Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Backend address", style = MaterialTheme.typography.titleMedium)
            Text(
                "The computer running make backend-run-lan. The emulator's name for it is " +
                    "${BackendSettings.DEFAULT_URL}. A phone needs the computer's own address, on the same Wi-Fi.",
                style = MaterialTheme.typography.bodySmall,
            )
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                label = { Text("Address") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = { viewModel.saveBackendUrl(text) }) { Text("Save") }
                OutlinedButton(onClick = {
                    if (viewModel.saveBackendUrl(text)) viewModel.testConnection()
                }) { Text("Save and test") }
            }
            viewModel.connectionMessage?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            Text("Saved: ${viewModel.backendUrl}", style = MaterialTheme.typography.bodySmall)
        }
    }
}
