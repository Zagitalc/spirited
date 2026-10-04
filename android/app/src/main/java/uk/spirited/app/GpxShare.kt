package uk.spirited.app

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import java.io.File

/** Hands a loop's GPX track to whatever app the person picks: a navigation app, files, a message. */
object GpxShare {
    private const val MIME = "application/gpx+xml"
    private const val DIR = "gpx"

    fun fileName(loopNumber: Int, minutes: Int) = "spirited-loop-$loopNumber-${minutes}min.gpx"

    /** Writes the file into the app's cache and opens the share sheet. Older files are removed first. */
    fun share(context: Context, gpx: String, loopNumber: Int, minutes: Int) {
        val dir = File(context.cacheDir, DIR).apply { mkdirs() }
        dir.listFiles()?.forEach { it.delete() }
        val file = File(dir, fileName(loopNumber, minutes))
        file.writeText(gpx)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        val send = Intent(Intent.ACTION_SEND)
            .setType(MIME)
            .putExtra(Intent.EXTRA_STREAM, uri)
            .putExtra(Intent.EXTRA_SUBJECT, "Spirited loop $loopNumber")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.startActivity(Intent.createChooser(send, "Share loop $loopNumber").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
