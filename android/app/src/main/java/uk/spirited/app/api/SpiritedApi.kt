package uk.spirited.app.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Talks to the Spirited backend. Cancelling the calling coroutine cancels the request. */
class SpiritedApi(
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        // Planning takes a couple of seconds on a laptop and more on a slow day.
        .readTimeout(60, TimeUnit.SECONDS)
        .callTimeout(90, TimeUnit.SECONDS)
        .build(),
) {
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    suspend fun health(baseUrl: String): ApiResult<Health> {
        val url = urlFor(baseUrl, "health") ?: return notAnAddress(baseUrl)
        return execute(Request.Builder().url(url).get().build(), baseUrl) {
            json.decodeFromString<Health>(it)
        }
    }

    suspend fun loops(
        baseUrl: String,
        lat: Double,
        lon: Double,
        minutes: Int,
        count: Int = 3,
    ): ApiResult<LoopsResponse> {
        val url = urlFor(baseUrl, "loops") ?: return notAnAddress(baseUrl)
        val body = json.encodeToString(LoopRequest(StartPoint(lat, lon), minutes, count))
            .toRequestBody("application/json".toMediaType())
        return execute(Request.Builder().url(url).post(body).build(), baseUrl) {
            json.decodeFromString<LoopsResponse>(it)
        }
    }

    private fun urlFor(baseUrl: String, path: String) =
        baseUrl.trim().trimEnd('/').toHttpUrlOrNull()?.newBuilder()?.addPathSegment(path)?.build()

    private fun notAnAddress(baseUrl: String) = ApiResult.Failed(ApiError.Unreachable(baseUrl.trim()))

    private suspend fun <T> execute(request: Request, baseUrl: String, parse: (String) -> T): ApiResult<T> {
        val address = baseUrl.trim().trimEnd('/')
        val response = try {
            http.newCall(request).await()
        } catch (e: IOException) {
            return ApiResult.Failed(ApiError.Unreachable(address))
        }
        return response.use { r ->
            val text = try {
                withContext(Dispatchers.IO) { r.body?.string().orEmpty() }
            } catch (e: IOException) {
                return@use ApiResult.Failed(ApiError.Unreachable(address))
            }
            when {
                r.isSuccessful -> try {
                    ApiResult.Ok(parse(text))
                } catch (e: SerializationException) {
                    ApiResult.Failed(ApiError.Unreadable("unexpected response"))
                } catch (e: IllegalArgumentException) {
                    ApiResult.Failed(ApiError.Unreadable("unexpected response"))
                }
                r.code == 422 -> ApiResult.Failed(ApiError.BadRequest(detailOf(text)))
                r.code == 503 -> ApiResult.Failed(ApiError.NotReady(detailOf(text)))
                else -> ApiResult.Failed(ApiError.Unreadable("status ${r.code}"))
            }
        }
    }

    /** FastAPI sends {"detail": "..."}; validation errors send a list, which is not for people. */
    private fun detailOf(body: String): String {
        val detail = try {
            (json.parseToJsonElement(body) as? JsonObject)?.get("detail")
        } catch (e: SerializationException) {
            null
        }
        return (detail as? JsonPrimitive)?.takeIf { it.isString }?.content ?: "the request was not accepted"
    }
}

private suspend fun Call.await(): Response = suspendCancellableCoroutine { continuation ->
    continuation.invokeOnCancellation { cancel() }
    enqueue(
        object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (!continuation.isCancelled) continuation.resumeWithException(e)
            }

            override fun onResponse(call: Call, response: Response) {
                continuation.resume(response)
            }
        },
    )
}
