package uk.spirited.app.map

import android.annotation.SuppressLint
import android.content.Context
import android.location.LocationManager
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.os.CancellationSignal

/** Asks the phone for its position once. Nothing is tracked and nothing is kept. */
object LocationFetcher {
    sealed interface Result {
        data class Found(
            val position: Position,
        ) : Result

        /** Location is switched off in the phone's settings, or no provider is available. */
        data object Unavailable : Result

        /** The phone did not give a position, for example with no signal indoors. */
        data object NoFix : Result
    }

    // The caller has checked the permission before calling this.
    @SuppressLint("MissingPermission")
    fun getOnce(
        context: Context,
        onResult: (Result) -> Unit,
    ): CancellationSignal? {
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        // The network provider answers within a second or two; GPS is the fallback for when it is off.
        val provider =
            listOf(LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER)
                .firstOrNull { manager.isProviderEnabled(it) }
        if (provider == null) {
            onResult(Result.Unavailable)
            return null
        }
        val signal = CancellationSignal()
        LocationManagerCompat.getCurrentLocation(
            manager,
            provider,
            signal,
            ContextCompat.getMainExecutor(context),
        ) { location ->
            onResult(
                if (location == null) Result.NoFix else Result.Found(Position(location.latitude, location.longitude)),
            )
        }
        return signal
    }
}
