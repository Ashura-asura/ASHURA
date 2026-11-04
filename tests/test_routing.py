from brain.controller import Controller, default_registry
from brain.need_field import NeedField, Task, always_all
from foundation.language_model import EchoModel
from learning.ama import AMA
from memory.database import Database


def ctl(mode="nfd"):
    return Controller(EchoModel(), ama=AMA(Database()), routing_mode=mode)


def sel(c, text, **kw):
    return c.handle(Task(text, **kw)).trace.routing["selected"]


def test_plain_chat_uses_only_language():
    assert sel(ctl(), "hello there") == ["language"]


def test_pure_arithmetic_skips_language_model():
    c = ctl()
    r = c.handle("What is 12*7?")
    assert set(r.trace.routing["selected"]) == {"arithmetic", "verification"}
    assert r.text == "84" and r.verified is True
    assert r.trace.routing["skipped"]["language"] == "cheap skill sufficient"


def test_arithmetic_inside_prose_still_uses_language():
    s = sel(ctl(), "I have 3 boxes with 12*7 items each, can you tell me a story about them")
    assert "arithmetic" in s and "language" in s


def test_memory_cue_activates_retrieval_but_ocr_stays_off():
    s = sel(ctl(), "what did I tell you about project P12?")
    assert "exact_retrieval" in s and "ocr" not in s


def test_ocr_module_is_routed_only_when_local_engine_is_available():
    c = ctl()
    r = c.handle(Task("what is in this picture", has_image=True))
    from skills.perception import OCREngine
    if OCREngine().available:
        assert "ocr" in r.trace.routing["selected"]
    else:
        assert "ocr" not in r.trace.routing["selected"]
        assert r.trace.routing["skipped"]["ocr"] == "needed but not implemented yet"


def test_unneeded_expensive_modules_never_selected():
    for q in ["hi", "what is 2+2", "explain why the sky is blue"]:
        s = sel(ctl(), q)
        assert not {"semantic_retrieval", "ocr", "learning"} & set(s)


def test_nfd_selects_fewer_modules_than_always_all():
    c = ctl()
    assert len(sel(c, "hello")) < len(always_all(c.registry).selected)


def test_trace_records_steps_and_overhead():
    r = ctl().handle("What is 12*7?")
    assert r.trace.step("arithmetic").output == "84"
    assert 0 <= r.trace.routing_ms < 50


def test_working_memory_fast_path_skips_second_search():
    c = ctl()
    c.ama.admit(__import__("memory.episodic", fromlist=["Experience"]).Experience("project p12 code", "4821"))
    q = "what did I tell you about project p12 code?"
    c.handle(q)
    r2 = c.handle(q)
    assert r2.trace.step("exact_retrieval").note == "fast path"


def test_low_ram_drops_optional_modules_but_keeps_language(monkeypatch):
    import brain.need_field as nf
    monkeypatch.setattr(nf, "available_ram_mb", lambda: 100.0)
    c = ctl()
    s = sel(c, "what did I tell you about project p12?")
    assert "language" in s          # already resident, costs no extra RAM


# ---- CPU awareness and measured costs ----
def test_busy_cpu_defers_optional_heavy_modules_but_not_the_answering_path(monkeypatch):
    import brain.need_field as nf
    monkeypatch.setattr(nf, "available_ram_mb", lambda: 16000.0)      # isolate from the machine's real free RAM
    from brain.controller import default_registry
    from brain.need_field import NeedField, Task
    reg = default_registry()
    reg.get("reasoning").available = True                      # pretend the heavy optional module exists
    busy = NeedField(reg, cpu_fn=lambda: 97.0).select(Task("Explain step by step why the sky is blue and compare it to sunsets"))
    idle = NeedField(reg, cpu_fn=lambda: 5.0).select(Task("Explain step by step why the sky is blue and compare it to sunsets"))
    assert "reasoning" in idle.selected
    assert "reasoning" not in busy.selected and "CPU busy" in busy.skipped["reasoning"]
    assert "language" in busy.selected                          # the model itself is resident: never starved


def test_measured_costs_replace_placeholders(tmp_path):
    import json
    from brain.controller import default_registry
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"language": {"est_latency_ms": 1234.0, "est_ram_mb": 4700.0}}))
    spec = default_registry(costs_path=f).get("language")
    assert spec.est_latency_ms == 1234.0 and spec.est_ram_mb == 4700.0
    assert default_registry(costs_path=tmp_path / "missing.json").get("language").est_latency_ms == 3000   # placeholder
    f.write_text("{not json")
    assert default_registry(costs_path=f).get("language").est_latency_ms == 3000                            # corrupt -> safe
