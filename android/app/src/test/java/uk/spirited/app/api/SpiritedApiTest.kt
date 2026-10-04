package uk.spirited.app.api

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class SpiritedApiTest {
    private lateinit var server: MockWebServer
    private lateinit var base: String
    private val api = SpiritedApi()

    @Before
    fun start() {
        server = MockWebServer()
        server.start()
        base = server.url("/").toString().trimEnd('/')
    }

    @After
    fun stop() {
        server.shutdown()
    }

    private val loopsJson =
        """
        {"loops": [{
          "distance_km": 74.6, "duration_min": 90, "score": 63.4,
          "shares": {"recommended": 0.81, "not_recommended": 0.07, "built_up": 0.12},
          "reuse_share": 0.03,
          "geometry": {"type": "LineString", "coordinates": [[-1.443, 51.4046], [-1.44, 51.41]]},
          "polyline": "abc", "gpx": "<gpx/>",
          "segments": [{"from_km": 0.0, "to_km": 6.2, "road": "B4000", "group": "recommended",
            "score": 68.0, "geometry": {"type": "LineString", "coordinates": [[-1.443, 51.4046]]}},
            {"from_km": 6.2, "to_km": 7.0, "road": "Mill Lane", "group": "not_recommended",
            "score": null, "geometry": {"type": "LineString", "coordinates": [[-1.44, 51.41]]}}],
          "warnings": ["7% of this loop is on roads we cannot vouch for"],
          "a_field_added_later": true
        }], "notes": []}
        """.trimIndent()

    private fun loops() = runBlocking { api.loops(base, 51.4046, -1.4430, 90) }

    @Test
    fun `a good answer is read, including fields it does not know`() {
        server.enqueue(MockResponse().setBody(loopsJson))
        val result = loops() as ApiResult.Ok
        val loop = result.value.loops.single()
        assertEquals(74.6, loop.distanceKm, 0.0)
        assertEquals(listOf("recommended", "not_recommended"), loop.segments.map { it.group })
        assertEquals(null, loop.segments[1].score)
        assertEquals(51.41, loop.geometry.coordinates[1][1], 0.0)
    }

    @Test
    fun `the request carries the start, the time and a count`() {
        server.enqueue(MockResponse().setBody("""{"loops": [], "notes": []}"""))
        loops()
        val sent = server.takeRequest()
        assertEquals("POST", sent.method)
        assertEquals("/loops", sent.path)
        val body = sent.body.readUtf8()
        assertTrue(body, """"start":{"lat":51.4046,"lon":-1.443}""" in body)
        assertTrue(body, """"duration_min":90""" in body)
        assertTrue(body, """"count":3""" in body)
    }

    @Test
    fun `422 shows the backend's reason`() {
        server.enqueue(MockResponse().setResponseCode(422).setBody("""{"detail": "Too close to the edge."}"""))
        val error = (loops() as ApiResult.Failed).error
        assertEquals(ApiError.BadRequest("Too close to the edge."), error)
        assertTrue("Too close to the edge." in error.message)
    }

    @Test
    fun `422 from request validation does not show raw JSON`() {
        server.enqueue(MockResponse().setResponseCode(422).setBody("""{"detail": [{"loc": ["body"], "msg": "x"}]}"""))
        val error = (loops() as ApiResult.Failed).error as ApiError.BadRequest
        assertEquals("the request was not accepted", error.detail)
    }

    @Test
    fun `503 means the service is not ready`() {
        server.enqueue(MockResponse().setResponseCode(503).setBody("""{"detail": "The routing service is not running."}"""))
        val error = (loops() as ApiResult.Failed).error
        assertEquals(ApiError.NotReady("The routing service is not running."), error)
    }

    @Test
    fun `nothing listening means unreachable`() {
        val dead = "http://127.0.0.1:1"
        val result = runBlocking { api.loops(dead, 51.0, -1.0, 90) } as ApiResult.Failed
        assertEquals(ApiError.Unreachable(dead), result.error)
    }

    @Test
    fun `an answer that is not the contract is unreadable`() {
        server.enqueue(MockResponse().setBody("""<html>captive portal</html>"""))
        val error = (loops() as ApiResult.Failed).error
        assertTrue(error is ApiError.Unreadable)
    }

    @Test
    fun `an unexpected status is unreadable and says which`() {
        server.enqueue(MockResponse().setResponseCode(500))
        val error = (loops() as ApiResult.Failed).error
        assertEquals(ApiError.Unreadable("status 500"), error)
    }

    @Test
    fun `health reports ok`() {
        server.enqueue(MockResponse().setBody("""{"status":"ok","version":"0.1.0"}"""))
        val result = runBlocking { api.health(base) } as ApiResult.Ok
        assertEquals("ok", result.value.status)
    }

    @Test
    fun `an address that is not a URL is unreachable`() {
        val result = runBlocking { api.health("not a url") } as ApiResult.Failed
        assertTrue(result.error is ApiError.Unreachable)
    }
}
