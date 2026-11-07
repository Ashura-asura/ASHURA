package com.ashura.tutor.domain.curriculum

import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.PracticeQuestion

/**
 * Small, hand-verified school-mathematics pack. Every expected answer is checked by
 * the unit tests against the deterministic evaluator, so content errors fail the build.
 * Authored for this app; not copied from any textbook.
 */
object SeedCurriculum {

    private const val SUBJECT = "Mathematics"

    private fun q(
        topic: String, n: Int, prompt: String, answer: String, explanation: String,
        hints: List<String> = emptyList(), wrong: Map<String, String> = emptyMap(),
        lowest: Boolean = false, accepted: List<String> = emptyList()
    ) = PracticeQuestion(
        id = "$topic:q$n", conceptId = topic, prompt = prompt, expectedAnswer = answer,
        explanation = explanation, hints = hints, misconceptionsByAnswer = wrong,
        requireLowestTerms = lowest, acceptedAnswers = accepted
    )

    val arithmetic = Topic(
        id = "math.arithmetic", subject = SUBJECT, title = "Arithmetic", level = LearnerLevel.SCHOOL,
        objectives = listOf(
            "Apply the order of operations: brackets, powers, multiplication/division, then addition/subtraction.",
            "Evaluate multi-step expressions without working strictly left to right."
        ),
        vocabulary = listOf("expression", "operation", "bracket", "power"),
        outline = listOf(
            "Why a fixed order of operations exists.",
            "Brackets first, then powers, then × and ÷ (left to right), then + and − (left to right).",
            "Worked example.", "Check your understanding."
        ),
        workedExample = "Evaluate 3 + 4 × 2.\nMultiplication comes before addition, so 4 × 2 = 8 first.\nThen 3 + 8 = 11.\nAnswer: 11 (not 14, which comes from adding first).",
        misconceptions = listOf(
            Misconception("arith.left_to_right", "Working strictly left to right and ignoring operation priority.",
                "Multiplication and division are done before addition and subtraction, unless brackets say otherwise."),
            Misconception("arith.right_to_left_division", "Dividing in the wrong direction in a chain of divisions.",
                "Equal-priority operations such as ÷ and ÷ are done left to right: 18 ÷ 3 ÷ 2 = 6 ÷ 2.")
        ),
        practice = listOf(
            q("math.arithmetic", 1, "Compute 3 + 4 * 2", "11", "4 × 2 = 8, then 3 + 8 = 11.",
                hints = listOf("Which operation has priority, + or ×?", "Do the multiplication first."),
                wrong = mapOf("14" to "arith.left_to_right")),
            q("math.arithmetic", 2, "Compute (3 + 4) * 2", "14", "Brackets first: 3 + 4 = 7, then 7 × 2 = 14.",
                hints = listOf("What do the brackets tell you to do first?")),
            q("math.arithmetic", 3, "Compute 10 - 2 * 3", "4", "2 × 3 = 6, then 10 − 6 = 4.",
                hints = listOf("Multiply before subtracting."), wrong = mapOf("24" to "arith.left_to_right")),
            q("math.arithmetic", 4, "Compute 18 / 3 / 2", "3", "Left to right: 18 ÷ 3 = 6, then 6 ÷ 2 = 3.",
                hints = listOf("Equal-priority operations go left to right."), wrong = mapOf("12" to "arith.right_to_left_division"))
        ),
        sourceRefs = listOf("ASHURA seed pack v1 (original content)")
    )

    val fractions = Topic(
        id = "math.fractions", subject = SUBJECT, title = "Fractions", level = LearnerLevel.SCHOOL,
        prerequisites = listOf("math.arithmetic"),
        objectives = listOf(
            "Add fractions by using a common denominator.",
            "Find a fraction of a quantity.",
            "Simplify a fraction to lowest terms."
        ),
        vocabulary = listOf("numerator", "denominator", "common denominator", "lowest terms"),
        outline = listOf(
            "A fraction is a part of a whole: numerator over denominator.",
            "Add and subtract only after the denominators match.",
            "A fraction of a quantity: divide by the denominator, multiply by the numerator.",
            "Worked example.", "Check your understanding."
        ),
        workedExample = "Evaluate 1/2 + 1/3.\nThe common denominator is 6: 1/2 = 3/6 and 1/3 = 2/6.\nAdd numerators only: 3/6 + 2/6 = 5/6.",
        misconceptions = listOf(
            Misconception("frac.add_across", "Adding numerators and denominators separately (1/2 + 1/3 = 2/5).",
                "Denominators name the size of the pieces; convert to equal-sized pieces first, then add only the numerators.")
        ),
        practice = listOf(
            q("math.fractions", 1, "Compute 1/2 + 1/3 as a fraction", "5/6", "Common denominator 6: 3/6 + 2/6 = 5/6.",
                hints = listOf("Make the denominators equal first.", "Use 6 as the common denominator."),
                wrong = mapOf("2/5" to "frac.add_across")),
            q("math.fractions", 2, "What is 3/4 of 20?", "15", "20 ÷ 4 = 5 per quarter, 5 × 3 = 15.",
                hints = listOf("Divide 20 by the denominator first.")),
            q("math.fractions", 3, "Simplify 6/8 to lowest terms", "3/4", "6 and 8 share the factor 2: 6/8 = 3/4.",
                hints = listOf("Find the largest number that divides both."), lowest = true)
        ),
        sourceRefs = listOf("ASHURA seed pack v1 (original content)")
    )

    val percentages = Topic(
        id = "math.percentages", subject = SUBJECT, title = "Ratios and percentages", level = LearnerLevel.SCHOOL,
        prerequisites = listOf("math.fractions"),
        objectives = listOf(
            "Find a percentage of a quantity.",
            "Increase a quantity by a percentage using multiplication.",
            "Share a total in a given ratio."
        ),
        vocabulary = listOf("percent", "ratio", "share", "multiplier"),
        outline = listOf(
            "Percent means per hundred: 20% = 20/100.",
            "Increase by p% = multiply by (1 + p/100).",
            "Ratio a:b of a total T: parts are T×a/(a+b) and T×b/(a+b).",
            "Worked example.", "Check your understanding."
        ),
        workedExample = "Increase 80 by 25%.\n25% of 80 is 20.\n80 + 20 = 100. (Equivalent: 80 × 1.25 = 100.)",
        misconceptions = listOf(
            Misconception("pct.add_points", "Adding the percentage as if it were an amount (80 + 25 = 105).",
                "A percentage is a fraction of the original quantity: find 25% of 80 first, then add it.")
        ),
        practice = listOf(
            q("math.percentages", 1, "What is 20% of 150?", "30", "20/100 × 150 = 30.", hints = listOf("20% = 0.2")),
            q("math.percentages", 2, "Increase 80 by 25%. What is the new value?", "100", "25% of 80 = 20; 80 + 20 = 100.",
                hints = listOf("Find 25% of 80 first."), wrong = mapOf("105" to "pct.add_points")),
            q("math.percentages", 3, "Share 40 in the ratio 3:5. What is the larger share?", "25", "3 + 5 = 8 parts; 40 ÷ 8 = 5 per part; 5 × 5 = 25.",
                hints = listOf("How many equal parts are there in total?"))
        ),
        sourceRefs = listOf("ASHURA seed pack v1 (original content)")
    )

    val linearEquations = Topic(
        id = "math.linear_equations", subject = SUBJECT, title = "Linear equations", level = LearnerLevel.SCHOOL,
        prerequisites = listOf("math.arithmetic", "math.fractions"),
        objectives = listOf(
            "Solve one-step and two-step equations by applying inverse operations to both sides.",
            "Check a solution by substituting it back."
        ),
        vocabulary = listOf("variable", "equation", "inverse operation", "coefficient"),
        outline = listOf(
            "An equation says two expressions are equal; keep it balanced.",
            "Undo operations in reverse order using inverse operations.",
            "Check by substitution.", "Worked example.", "Check your understanding."
        ),
        workedExample = "Solve 2x + 3 = 11.\nSubtract 3 from both sides: 2x = 8.\nDivide both sides by 2: x = 4.\nCheck: 2 × 4 + 3 = 11 ✓.",
        misconceptions = listOf(
            Misconception("lin.wrong_inverse", "Using the same operation instead of the inverse (adding 3 instead of subtracting).",
                "To remove + 3 you subtract 3 from both sides; to remove × 2 you divide both sides by 2.")
        ),
        practice = listOf(
            q("math.linear_equations", 1, "Solve 2x + 3 = 11. What is x?", "4", "2x = 8, so x = 4.",
                hints = listOf("Undo the + 3 first."), wrong = mapOf("7" to "lin.wrong_inverse")),
            q("math.linear_equations", 2, "Solve 3x - 5 = 10. What is x?", "5", "3x = 15, so x = 5.",
                hints = listOf("Add 5 to both sides.")),
            q("math.linear_equations", 3, "Solve x / 4 = 6. What is x?", "24", "Multiply both sides by 4: x = 24.",
                hints = listOf("Division is undone by multiplication."), wrong = mapOf("1.5" to "lin.wrong_inverse"))
        ),
        sourceRefs = listOf("ASHURA seed pack v1 (original content)")
    )

    val pack = CurriculumPack("ashura.seed.math", 1, listOf(arithmetic, fractions, percentages, linearEquations))
}
