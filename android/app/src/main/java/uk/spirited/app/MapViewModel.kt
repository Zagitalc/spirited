package uk.spirited.app

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import uk.spirited.app.api.ApiResult
import uk.spirited.app.api.LoopsResponse
import uk.spirited.app.api.SpiritedApi
import uk.spirited.app.map.Position

sealed interface LoopsState {
    data object Idle : LoopsState

    data object Loading : LoopsState

    data class Loaded(val response: LoopsResponse) : LoopsState

    data class Error(val message: String) : LoopsState
}

/** Holds what the person has chosen and what the backend said, across rotation and backgrounding. */
class MapViewModel(application: Application) : AndroidViewModel(application) {
    private val settings = BackendSettings(application)
    private val api = SpiritedApi()
    private var job: Job? = null

    var start by mutableStateOf<Position?>(null)
        private set
    var minutes by mutableIntStateOf(DEFAULT_MINUTES)
        private set
    var loops by mutableStateOf<LoopsState>(LoopsState.Idle)
        private set
    var selectedLoop by mutableIntStateOf(0)
        private set
    var backendUrl by mutableStateOf(settings.url)
        private set
    var connectionMessage by mutableStateOf<String?>(null)
        private set

    fun chooseStart(position: Position) {
        start = position
        forgetLoops()
    }

    fun chooseMinutes(value: Int) {
        minutes = value.coerceIn(MIN_MINUTES, MAX_MINUTES)
        forgetLoops()
    }

    /** A request for an old start or time is no longer wanted, so it is cancelled and its answer dropped. */
    private fun forgetLoops() {
        job?.cancel()
        loops = LoopsState.Idle
        selectedLoop = 0
    }

    fun chooseLoop(index: Int) {
        val found = (loops as? LoopsState.Loaded)?.response?.loops ?: return
        if (index in found.indices) selectedLoop = index
    }

    fun requestLoops() {
        val here = start ?: return
        // A second tap while waiting does nothing.
        if (loops is LoopsState.Loading) return
        loops = LoopsState.Loading
        job = viewModelScope.launch {
            loops = when (val result = api.loops(backendUrl, here.lat, here.lon, minutes)) {
                is ApiResult.Ok -> {
                    selectedLoop = 0
                    LoopsState.Loaded(result.value)
                }
                is ApiResult.Failed -> LoopsState.Error(result.error.message)
            }
        }
    }

    /** Returns false, with a message, if the text cannot be an address. */
    fun saveBackendUrl(text: String): Boolean {
        val tidy = BackendSettings.normalise(text)
        if (tidy == null) {
            connectionMessage = "That is not a valid address. Try something like http://192.168.50.10:8000"
            return false
        }
        settings.url = tidy
        backendUrl = tidy
        connectionMessage = null
        forgetLoops()
        return true
    }

    fun testConnection() {
        connectionMessage = "Testing..."
        viewModelScope.launch {
            connectionMessage = when (val result = api.health(backendUrl)) {
                is ApiResult.Ok -> "Connected: the backend says ${result.value.status}."
                is ApiResult.Failed -> result.error.message
            }
        }
    }

    fun clearConnectionMessage() {
        connectionMessage = null
    }

    companion object {
        const val MIN_MINUTES = 20
        const val MAX_MINUTES = 240
        const val DEFAULT_MINUTES = 90
    }
}
