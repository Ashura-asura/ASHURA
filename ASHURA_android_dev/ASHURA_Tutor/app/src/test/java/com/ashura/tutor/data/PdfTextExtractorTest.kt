package com.ashura.tutor.data

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

/** Round-trips a small generated PDF through PdfBox-Android on the JVM (Robolectric provides the context). */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class PdfTextExtractorTest {

    @Before fun setUp() {
        PDFBoxResourceLoader.init(ApplicationProvider.getApplicationContext<Application>())
    }

    private fun samplePdf(): File {
        val file = File.createTempFile("ashura-pdf-test", ".pdf")
        val document = PDDocument()
        try {
            listOf(
                "Photosynthesis converts light energy into glucose.",
                "Mitochondria release energy from glucose in cells."
            ).forEachIndexed { index, line ->
                val page = PDPage()
                document.addPage(page)
                val content = PDPageContentStream(document, page)
                content.beginText()
                content.setFont(PDType1Font.HELVETICA, 12f)
                content.newLineAtOffset(50f, 700f)
                content.showText(line)
                content.endText()
                content.close()
            }
            document.save(file)
        } finally {
            document.close()
        }
        return file
    }

    @Test fun embeddedTextIsExtractedPerPage() {
        val file = samplePdf()
        try {
            val result = PdfTextExtractor.extract(file)
            assertTrue("extraction failed: $result", result is PdfTextExtractor.Result.Success)
            val success = result as PdfTextExtractor.Result.Success
            assertEquals(2, success.totalPages)
            assertEquals(2, success.pages.size)
            assertEquals(1, success.pages[0].pageNumber)
            assertTrue(success.pages[0].text.contains("Photosynthesis"))
            assertEquals(2, success.pages[1].pageNumber)
            assertTrue(success.pages[1].text.contains("Mitochondria"))
        } finally {
            file.delete()
        }
    }

    @Test fun pageLimitIsEnforcedAndReported() {
        val file = samplePdf()
        try {
            val result = PdfTextExtractor.extract(file, maxPages = 1) as PdfTextExtractor.Result.Success
            assertEquals(1, result.pages.size)
            assertEquals(2, result.totalPages)
            assertTrue(result.truncated)
        } finally {
            file.delete()
        }
    }
}
