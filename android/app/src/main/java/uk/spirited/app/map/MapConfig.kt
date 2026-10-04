package uk.spirited.app.map

/** Where the map comes from and where it first looks. Nothing else in the app knows the style address. */
object MapConfig {
    // OpenFreeMap needs no key and allows use from an app (terms read 2026-10-04). Check the
    // address against https://openfreemap.org/quick_start/ if the map ever comes up blank.
    const val STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"

    // The middle of the covered area: Berkshire and the counties around it.
    const val INITIAL_LAT = 51.45
    const val INITIAL_LON = -1.05
    const val INITIAL_ZOOM = 9.0
}
