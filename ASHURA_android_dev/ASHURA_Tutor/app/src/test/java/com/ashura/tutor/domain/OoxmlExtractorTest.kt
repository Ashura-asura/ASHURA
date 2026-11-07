package com.ashura.tutor.domain

import com.ashura.tutor.domain.library.OoxmlExtractor
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class OoxmlExtractorTest {

    @Test fun docxExtractsParagraphsRunsAndTables() {
        val doc = """
            <?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>Photosynthesis</w:t></w:r><w:r><w:t xml:space="preserve"> converts light.</w:t></w:r></w:p>
                <w:p><w:r><w:t>Chlorophyll absorbs light.</w:t></w:r></w:p>
                <w:tbl><w:tr>
                  <w:tc><w:p><w:r><w:t>Cell</w:t></w:r></w:p></w:tc>
                  <w:tc><w:p><w:r><w:t>Nucleus</w:t></w:r></w:p></w:tc>
                </w:tr></w:tbl>
              </w:body>
            </w:document>
        """.trimIndent()
        val result = extract(OoxmlExtractor.Kind.DOCX, "word/document.xml" to doc)
        assertTrue(result.toString(), result is OoxmlExtractor.Result.Success)
        val text = (result as OoxmlExtractor.Result.Success).text
        assertTrue(text.contains("Photosynthesis converts light."))
        assertTrue(text.contains("Chlorophyll absorbs light."))
        assertTrue(text.contains("Cell"))
        assertTrue(text.contains("Nucleus"))
    }

    @Test fun xlsxExtractsSharedStringsNumbersFormulasAndSheetNames() {
        val sharedStrings = """
            <?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Name</t></si>
              <si><t>Score</t></si>
              <si><r><t>Al</t></r><r><t>ice</t></r></si>
            </sst>
        """.trimIndent()
        val sheet = """
            <?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
                <row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>42</v></c><c r="C2"><f>B2*2</f><v>84</v></c></row>
              </sheetData>
            </worksheet>
        """.trimIndent()
        val workbook = """
            <?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="Marks" sheetId="1" r:id="rId1"/></sheets>
            </workbook>
        """.trimIndent()
        val rels = """
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
            </Relationships>
        """.trimIndent()

        val result = extract(
            OoxmlExtractor.Kind.XLSX,
            "xl/sharedStrings.xml" to sharedStrings,
            "xl/worksheets/sheet1.xml" to sheet,
            "xl/workbook.xml" to workbook,
            "xl/_rels/workbook.xml.rels" to rels
        )
        assertTrue(result.toString(), result is OoxmlExtractor.Result.Success)
        val text = (result as OoxmlExtractor.Result.Success).text
        assertTrue(text.contains("[Sheet: Marks]"))
        assertTrue(text.contains("Name"))
        assertTrue(text.contains("Score"))
        assertTrue(text.contains("Alice"))
        assertTrue(text.contains("A2: Alice"))
        assertTrue(text.contains("B2: 42"))
        assertTrue(text.contains("C2: 84 [=B2*2]"))
    }

    @Test fun pptxExtractsSlidesInNumericOrderWithNotes() {
        fun slide(text: String) = """
            <?xml version="1.0" encoding="UTF-8"?>
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                   xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree><p:sp><p:txBody>
                <a:p><a:r><a:t>$text</a:t></a:r></a:p>
              </p:txBody></p:sp></p:spTree></p:cSld>
            </p:sld>
        """.trimIndent()

        val result = extract(
            OoxmlExtractor.Kind.PPTX,
            "ppt/slides/slide10.xml" to slide("Tenth"),
            "ppt/slides/slide2.xml" to slide("Second"),
            "ppt/notesSlides/notesSlide2.xml" to slide("Speaker note"),
            "ppt/slides/slide1.xml" to slide("First")
        )
        assertTrue(result.toString(), result is OoxmlExtractor.Result.Success)
        val text = (result as OoxmlExtractor.Result.Success).text
        assertTrue(text.indexOf("First") < text.indexOf("Second"))
        assertTrue(text.indexOf("Second") < text.indexOf("Tenth"))
        assertTrue(text.contains("Speaker note"))
    }

    @Test fun rejectsCorruptArchiveAndMissingParts() {
        assertTrue(
            OoxmlExtractor.extract(OoxmlExtractor.Kind.DOCX, ByteArrayInputStream(byteArrayOf(1, 2, 3)))
                is OoxmlExtractor.Result.Failure
        )
        assertTrue(extract(OoxmlExtractor.Kind.DOCX, "other.xml" to "<x/>") is OoxmlExtractor.Result.Failure)
        assertTrue(
            extract(OoxmlExtractor.Kind.DOCX, "word/document.xml" to "<w:document>")
                is OoxmlExtractor.Result.Failure
        )
    }

    @Test fun rejectsOversizedExpansion() {
        val big = "a".repeat((OoxmlExtractor.MAX_PART_BYTES + 1024).toInt())
        val result = extract(OoxmlExtractor.Kind.DOCX, "word/document.xml" to big)
        assertTrue(result.toString(), result is OoxmlExtractor.Result.Failure)
        assertTrue((result as OoxmlExtractor.Result.Failure).reason.contains("larger"))
    }

    private fun extract(kind: OoxmlExtractor.Kind, vararg entries: Pair<String, String>): OoxmlExtractor.Result =
        OoxmlExtractor.extract(kind, ByteArrayInputStream(zip(entries.toList())))

    private fun zip(entries: List<Pair<String, String>>): ByteArray {
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { zip ->
            for ((name, content) in entries) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(content.toByteArray(Charsets.UTF_8))
                zip.closeEntry()
            }
        }
        return out.toByteArray()
    }
}
