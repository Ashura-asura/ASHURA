from evaluation.ocr_benchmark import error_rate, normalize


def test_ocr_normalization_and_error_rates():
    assert normalize(" A  B\n") == "a b"
    assert error_rate("hello world", "hello world", "word") == 0
    assert error_rate("hello wurld", "hello world", "char") > 0
