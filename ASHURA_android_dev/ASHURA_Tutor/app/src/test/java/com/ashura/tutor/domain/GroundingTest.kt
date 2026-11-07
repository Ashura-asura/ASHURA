package com.ashura.tutor.domain

import com.ashura.tutor.data.FtsQuery
import com.ashura.tutor.domain.library.GroundingPolicy
import com.ashura.tutor.domain.library.PassageRef
import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
import com.ashura.tutor.domain.runtime.PromptBuilder
import com.ashura.tutor.domain.runtime.UnavailableModelRuntime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.startCoroutine

/** Runs a suspend block that never actually suspends (all fakes here complete immediately). */
private fun <T> runSuspend(block: suspend () -> T): T {
    var out: Result<T>? = null
    block.startCoroutine(Continuation(EmptyCoroutineContext) { out = it })
    return out!!.getOrThrow()
}

class GroundingTest {
    @Test fun questionKeywordsDropStopwordsAndKeepDistinctiveTerms() {
        assertEquals(listOf("newton", "first", "law"), FtsQuery.keywords("What does Newton's first law say?").let { it - "s" })
        assertEquals(listOf("photosynthesis", "chloroplast"), FtsQuery.keywords("Explain photosynthesis in the chloroplast"))
        assertTrue(FtsQuery.keywords("what is it?").isEmpty())
        assertNull(FtsQuery.forQuestion("why how what"))
    }

    @Test fun questionQueryIsOrOfQuotedPrefixTermsAndInjectionSafe() {
        assertEquals("\"mitochondria\"* OR \"energy\"*", FtsQuery.forQuestion("Mitochondria energy?"))
        val q = FtsQuery.forQuestion("cell\" OR NEAR(a b) -- DROP")!!
        assertFalse(q.contains("NEAR("))
        assertTrue(q.split(" OR ").all { it.startsWith("\"") && it.endsWith("\"*") })
        assertEquals(8, FtsQuery.keywords((1..30).joinToString(" ") { "term$it" }).size)
    }

    @Test fun nepaliQuestionWordsSurvive() {
        assertEquals(listOf("प्रकाश", "संश्लेषण"), FtsQuery.keywords("प्रकाश संश्लेषण"))
    }

    @Test fun groundingPolicyBoundsDedupesAndCitesInOrder() {
        val hits = listOf(
            PassageRef("Bio", 0, "Cells are the basic unit of life."),
            PassageRef("Bio", 0, "cells are the   basic unit of life."),   // duplicate
            PassageRef("Bio", 1, "Mitochondria make ATP."),
            PassageRef("Bio", 2, "Third passage from the same note."),       // per-source cap
            PassageRef("Physics", 4, "Force equals mass times acceleration."),
            PassageRef("Chem", 0, "x".repeat(5000))                            // over the size budget
        )
        val g = GroundingPolicy.select(hits)
        assertEquals(listOf("Bio · passage 1", "Bio · passage 2", "Physics · passage 5"), g.snippets.map { it.sourceLabel })
        assertEquals(listOf("[1] Bio · passage 1", "[2] Bio · passage 2", "[3] Physics · passage 5"), g.citations)
        assertTrue(GroundingPolicy.select(emptyList()).snippets.isEmpty())
    }

    private fun controller(model: ModelRuntime = UnavailableModelRuntime()) =
        TaskController(model, mapOf("calculator" to CalculatorTool()))

    @Test fun offlineAnswerWithNotesIsExtractiveAndCited() {
        val ctx = GroundingPolicy.select(listOf(PassageRef("Bio", 0, "Mitochondria make ATP."))).snippets
        val req = TutorRequest("What do mitochondria do?", retrievedContext = ctx, notesSearched = true)
        val r = runSuspend { controller().let { it.execute(it.route(req.question), req) } }
        assertEquals(ResponseMode.OFFLINE_FALLBACK, r.mode)
        assertTrue(r.answer.contains("Mitochondria make ATP."))
        assertTrue(r.answer.contains("not explained by a model"))
        assertEquals(listOf("[1] Bio · passage 1"), r.citations)
        assertTrue(r.limitation!!.contains("Extractive"))
    }

    @Test fun offlineAnswerSaysWhenNotesHadNothing() {
        val req = TutorRequest("What is entropy?", notesSearched = true)
        val r = runSuspend { controller().let { it.execute(it.route(req.question), req) } }
        assertTrue(r.answer.contains("found nothing relevant"))
        assertTrue(r.citations.isEmpty())
        val unsearched = runSuspend { controller().let { c -> c.execute(c.route("What is entropy?"), TutorRequest("What is entropy?")) } }
        assertFalse(unsearched.answer.contains("found nothing relevant"))
    }

    @Test fun calculatorStillWinsOverNotes() {
        val ctx = GroundingPolicy.select(listOf(PassageRef("Bio", 0, "irrelevant"))).snippets
        val req = TutorRequest("3 + 4 * 2", retrievedContext = ctx, notesSearched = true)
        val r = runSuspend { controller().let { it.execute(it.route(req.question), req) } }
        assertEquals(ResponseMode.DETERMINISTIC, r.mode)
        assertTrue(r.answer.endsWith("= 11"))
        assertTrue(r.citations.isEmpty())
    }

    private class FakeModel : ModelRuntime {
        var lastRequest: TutorRequest? = null
        override val isAvailable = true
        override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse {
            lastRequest = request
            return TutorResponse("ATP is made in mitochondria [1].", ResponseMode.LOCAL_MODEL)
        }
        override fun unload() = Unit
    }

    @Test fun modelPathGetsBoundedContextAndCitationsAreAttached() {
        val model = FakeModel()
        val ctx = GroundingPolicy.select(listOf(PassageRef("Bio", 0, "Mitochondria make ATP."))).snippets
        val req = TutorRequest("Where is ATP made?", retrievedContext = ctx, notesSearched = true)
        val r = runSuspend { controller(model).let { it.execute(it.route(req.question), req) } }
        assertEquals(ResponseMode.LOCAL_MODEL, r.mode)
        assertEquals(listOf("[1] Bio · passage 1"), r.citations)
        assertEquals(1, model.lastRequest!!.retrievedContext.size)
        assertTrue(r.limitation!!.contains("not independently verified"))
    }

    @Test fun promptAsksForCitationsAndStaysDelimited() {
        val ctx = GroundingPolicy.select(listOf(PassageRef("Bio", 0, "Mitochondria make ATP."))).snippets
        val p = PromptBuilder.build(TutorRequest("Where is ATP made?", retrievedContext = ctx), GenerationLimits())
        assertTrue(p.contains("cite it as [n]"))
        assertTrue(p.contains("<evidence id=\"1\""))
        assertTrue(p.contains("do not cover it"))
    }
}
