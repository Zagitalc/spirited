package uk.spirited.app.api

sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>

    data class Failed(val error: ApiError) : ApiResult<Nothing>
}

/** The four ways a request can go wrong, each with a sentence that is safe to show to a person. */
sealed interface ApiError {
    val message: String

    /** The backend refused the request (422): a start too near the edge, or no road nearby. */
    data class BadRequest(val detail: String) : ApiError {
        override val message get() = "That start will not work: $detail"
    }

    /** The backend is up but cannot plan yet (503): routing is not running or scores are missing. */
    data class NotReady(val detail: String) : ApiError {
        override val message get() = "The Spirited service is not ready: $detail"
    }

    /** Nothing answered: wrong address, backend stopped, or the phone is on another network. */
    data class Unreachable(val address: String) : ApiError {
        override val message get() =
            "Could not reach the backend at $address. Is it running, and is the phone on the same Wi-Fi as the computer?"
    }

    /** Something answered, but not in a way the app understands. */
    data class Unreadable(val why: String) : ApiError {
        override val message get() = "The backend answered with something the app could not read ($why)."
    }
}
