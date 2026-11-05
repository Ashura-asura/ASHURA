from evaluation.judge import judge, judge_both, strip_echo, words

ARITH = {"prompt": "What is 17 * 23?", "accept": ["391"]}
DIV = {"prompt": "What is 144 divided by 12?", "accept": ["12"]}
YESNO = {"prompt": "Reply with exactly one word: yes or no. Is the sun a star?", "accept": ["yes"], "match": "first_word"}
ES = {"prompt": "Translate 'good morning' into Spanish.", "accept": ["buenos días", "buenos dias"]}


def test_echoing_the_prompt_does_not_pass():
    for item in (DIV, YESNO):
        assert judge_both("[echo] " + item["prompt"], item) == {"lenient": False, "strict": False}


def test_correct_answers_pass_including_verbose_ones():
    assert judge("391", ARITH, strict=True)
    assert judge("17 * 23 = 391.", ARITH, strict=True)
    assert judge("The answer is 12.", DIV, strict=True)


def test_whole_token_matching():
    assert not judge("The answer is 3910", ARITH)
    assert not judge("It is 1,391", ARITH)
    assert not judge("It is 12.5", DIV)
    assert judge("It is 1,024", {"prompt": "2 to the power of 10?", "accept": ["1024"]})


def test_accents_are_normalised():
    assert judge("Buenos días", ES, strict=True) and judge("buenos dias", ES, strict=True)


def test_decimal_padding_is_normalised():
    assert judge("4.000 m/s^2", {"prompt": "acceleration?", "accept": ["4"]})
    assert judge("9.000 J", {"prompt": "energy?", "accept": ["9"]})
    assert not judge("12.500", DIV)


def test_strict_requires_answer_in_first_line_and_first_word_for_yes_no():
    assert judge("Yes.", YESNO, strict=True)
    assert not judge("No, although some say yes", YESNO, strict=True)
    assert judge("No, although some say yes", {"prompt": "x", "accept": ["yes"]}, strict=False)   # lenient only
    assert not judge("Let me think.\nThe answer is 391", ARITH, strict=True)
    assert judge("Let me think.\nThe answer is 391", ARITH, strict=False)


def test_echo_run_removed_but_answer_kept():
    out = words("144 divided by 12 equals 12")
    cleaned = strip_echo(out, DIV["prompt"])
    assert "equals" in cleaned and cleaned.count("12") == 1      # echoed "12" removed, answer "12" kept
    assert judge("144 divided by 12 equals 12", DIV, strict=True)
    assert not judge("144 divided by 12 equals 13", DIV, strict=True)
